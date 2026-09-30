"""Automated review of the Roshan Mustaqbil data and screens.

Checks the rules the app depends on (students enroll in person, so the
enrollment day is a visit; each rule gives the same students in Python and
in the database; the call lists add up and don't overlap), basic data
quality, that the administrator is the only sign-in, and that removed
wording and broken styles haven't crept back in.

    python manage.py review_rm

Exits with status 1 if any check fails, so it can run in CI or before a demo.
"""

import re
import sys
from collections import Counter
from pathlib import Path

import tinycss2
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q
from django.utils import timezone

from base.rm import (
    ALL_STATUSES, ENGAGEMENT_KEYS, ENGAGEMENT_LABELS, ENROLLMENT_VISIT, GOAL_KEYS, MOVED_ON, engagement_q, needs_call,
    needs_call_q, no_return_q, normalize_phone, rm_visits, student_queryset, valid_mobile, with_last_visit,
)
from base.rm_common import student_values
from employee.models import StudentProfile

REMOVED_WORDING = (
    ("Never Attended", re.compile(r"Never Attended")),
    ('"Never came" status', re.compile(r"never came(?! back)", re.IGNORECASE)),
    ("staff roles (front desk / coordinator)", re.compile(r"\bfront desk\b|\bcoordinator\b", re.IGNORECASE)),
    ("preparation stage and exam year", re.compile(r"preparation stage|prep_stage|exam year|target_year|exam_year", re.IGNORECASE)),
)


class Command(BaseCommand):
    help = "Check Roshan Mustaqbil data invariants, call lists, data quality, access and templates."

    def add_arguments(self, parser):
        parser.add_argument("--examples", type=int, default=3, help="How many offending records to list per failed check.")

    def handle(self, *args, **options):
        self.examples = options["examples"]
        self.passed = self.failed = 0
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        try:
            "✓✗".encode(encoding)
            self.marks = ("✓", "✗")
        except (UnicodeEncodeError, LookupError):
            self.marks = ("PASS", "FAIL")

        today = timezone.localdate()
        students = with_last_visit(student_queryset(), today)
        rows = student_values(today)
        visits = rm_visits()

        self.section("Model invariants")
        per_student = dict(visits.order_by().values("employee_id").annotate(total=Count("id")).values_list("employee_id", "total"))
        no_visits = [student for student in student_queryset().select_related(None).only("id", "badge_id") if student.id not in per_student]
        self.verify("Every student has at least one visit", not no_visits, self.list(no_visits))
        early = visits.filter(attendance_date__lt=F("employee_id__rm_profile__registration_date"))
        self.verify("No visit is dated before the student enrolled", not early.exists(), self.visit_list(early))
        future = visits.filter(attendance_date__gt=today)
        self.verify("No visit is dated in the future", not future.exists(), self.visit_list(future))
        after_moving_on = visits.filter(
            ~Q(employee_id__rm_profile__outcome=""), attendance_date__gt=F("employee_id__rm_profile__outcome_date"),
        )
        self.verify("Nobody who moved on has come back since (a visit clears it)", not after_moving_on.exists(), self.visit_list(after_moving_on))
        with_login = student_queryset().filter(employee_user_id__isnull=False, employee_user_id__is_active=True)
        self.verify("No student has an active login (students are records, not users)", not with_login.exists(), self.list(with_login))
        with_hr = student_queryset().filter(employee_work_info__isnull=False)
        self.verify("No student has an HR work record (which brings a payroll contract)", not with_hr.exists(), self.list(with_hr))

        self.section("Enrollment visit (students enroll in person)")
        enrollment = visits.filter(request_description=ENROLLMENT_VISIT)
        per_enrollment = Counter(enrollment.values_list("employee_id", flat=True))
        profiles = dict(StudentProfile.objects.filter(employee__is_active=True).values_list("employee_id", "registration_date"))
        missing = [student_id for student_id in profiles if per_enrollment[student_id] == 0]
        duplicated = [student_id for student_id, total in per_enrollment.items() if total > 1]
        self.verify("Every student has exactly one enrollment visit", not missing and not duplicated,
                    f"{len(missing)} without one, {len(duplicated)} with several" if missing or duplicated else "")
        misdated = [
            student_id for student_id, day in enrollment.values_list("employee_id", "attendance_date")
            if profiles.get(student_id) and day != profiles[student_id]
        ]
        self.verify("The enrollment visit is on the enrollment date", not misdated, f"{len(misdated)} on another date" if misdated else "")

        self.section("Rules give the same students in Python and in the database")
        by_python = {row["id"] for row in rows if row["no_return"]}
        by_query = set(students.filter(no_return_q(today)).values_list("id", flat=True))
        self.verify(f"Didn't come back after enrolling ({len(by_python)} students)", by_python == by_query, self.differ(by_python, by_query))
        for status in ALL_STATUSES:
            in_python = {row["id"] for row in rows if row["status"] == status}
            in_query = set(students.filter(engagement_q(status, today)).values_list("id", flat=True))
            self.verify(f"{ENGAGEMENT_LABELS[status]} ({len(in_python)})", in_python == in_query, self.differ(in_python, in_query))
        due_python = {row["id"] for row in rows if row["status"] != MOVED_ON and needs_call(row["status"], row["last_visit"], row, today)}
        due_query = set(students.filter(needs_call_q(today)).values_list("id", flat=True))
        self.verify(f"Stopped coming and due a call ({len(due_python)})", due_python == due_query, self.differ(due_python, due_query))

        self.section("Call lists")
        from base.rm_students import QUEUES, queue_counts, queue_membership, queue_students

        queues = {}
        for key, _, _ in QUEUES:
            members = queue_students(key, today)
            queues[key] = {student.id for student in members}
        overlaps = [
            f"{first}/{second}: {len(queues[first] & queues[second])}"
            for index, first in enumerate(queues) for second in list(queues)[index + 1:]
            if queues[first] & queues[second]
        ]
        self.verify("No student is on two call lists", not overlaps, ", ".join(overlaps))
        counts = queue_counts(today)
        total = sum(counts.values())
        self.verify(f"\"Waiting for a call\" is the same on the dashboard, the call list and the call sheet ({total})",
                    total == len(queue_membership(today)) == sum(len(ids) for ids in queues.values()))
        moved = set(students.filter(~Q(rm_profile__outcome="")).values_list("id", flat=True))
        moved_in_queue = set().union(*queues.values()) & moved
        self.verify("Moved-on students are never on a call list", not moved_in_queue, f"{len(moved_in_queue)} students" if moved_in_queue else "")
        self.verify(f"The first list has students ({counts['once']})", bool(counts["once"]), warn_only=True)

        self.section("Data quality")
        undated = StudentProfile.objects.filter(registration_date__isnull=True)
        self.verify("Every student has an enrollment date", not undated.exists(), f"{undated.count()} without" if undated.exists() else "")
        bad_phones = [student for student in student_queryset().select_related(None).only("id", "badge_id", "phone") if not valid_mobile(normalize_phone(student.phone))]
        self.verify("Every phone number is a 10-digit mobile number", not bad_phones, self.list(bad_phones))
        shared = [phone for phone, count in Counter(student_queryset().values_list("phone", flat=True)).items() if count > 1]
        self.verify(f"Shared phone numbers are few ({len(shared)}; siblings often share)", len(shared) <= max(20, len(profiles) // 20), warn_only=True)
        twins = [key for key, count in Counter(
            (first.lower(), (last or "").lower(), phone) for first, last, phone in student_queryset().values_list("employee_first_name", "employee_last_name", "phone")
        ).items() if count > 1]
        self.verify("No student is enrolled twice (same name and phone)", not twins, f"{len(twins)} pairs, e.g. {' '.join(twins[0][:2]).title()}" if twins else "", warn_only=True)
        sundays = visits.filter(attendance_date__week_day=1).count()
        self.verify("No visits on Sundays, when the centre is closed", not sundays, f"{sundays} visits", warn_only=True)

        self.section("Access")
        from horilla_auth.models import HorillaUser

        users = list(HorillaUser.objects.filter(is_active=True).values_list("username", "is_superuser"))
        admins = [name for name, superuser in users if superuser]
        self.verify(f"The administrator is the only sign-in ({', '.join(name for name, _ in users) or 'none'})",
                    len(users) == 1 and len(admins) == 1, warn_only=True)

        self.section("Templates, docs and styles")
        base = Path(settings.BASE_DIR)
        sources = [*(base / "templates" / "rm").rglob("*.html"), *(base / "docs").rglob("*.md"), *(base / "docs").rglob("*.csv"),
                   base / "README.md", base / "static" / "rm" / "rm.js", *(base / "base").glob("rm*.py")]
        texts = {path: path.read_text(encoding="utf-8") for path in sources if path.exists()}
        for label, pattern in REMOVED_WORDING:
            hits = sorted({path.name for path, text in texts.items() if pattern.search(text)})
            self.verify(f"Removed wording is gone: {label}", not hits, ", ".join(hits))
        css = (base / "static" / "rm" / "rm.css").read_text(encoding="utf-8")
        rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
        # A declaration block left without its selector silently swallows the
        # next rule (browsers read the stray text as part of its selector).
        broken = [
            f"line {rule.source_line}" for rule in rules
            if rule.type == "error" or (rule.type == "qualified-rule" and ";" in tinycss2.serialize(rule.prelude))
        ]
        self.verify("rm.css has no broken rules", not broken, ", ".join(broken))
        selectors = " ".join(tinycss2.serialize(rule.prelude) for rule in rules if rule.type == "qualified-rule")
        keys = set(ENGAGEMENT_KEYS.values()) | set(GOAL_KEYS.values()) | {"muted", "call", "good", "neutral", "lost", "female", "male", "none"}
        keys |= {f"age-{index}" for index in range(7)}
        unstyled = sorted(key for key in keys if not re.search(rf"\.k-{re.escape(key)}(?![\w-])", selectors))
        self.verify("Every colour key the charts use has a colour", not unstyled, ", ".join(unstyled))

        self.section("Students by status")
        statuses = Counter(row["status"] for row in rows)
        table = [(ENGAGEMENT_LABELS[status], statuses[status]) for status in ALL_STATUSES]
        table.append(("Total enrolled", sum(statuses.values())))
        width = max(len(label) for label, _ in table)
        for label, count in table:
            self.stdout.write(f"  {label.ljust(width)}  {count:>5}")
        self.stdout.write(f"  Didn't come back after enrolling (across the statuses above): {len(by_python)}")
        self.stdout.write(f"  Waiting for a call: {total} ({', '.join(f'{label} {counts[key]}' for key, label, _ in QUEUES)})")

        self.stdout.write("")
        summary = f"{self.passed} checks passed, {self.failed} failed"
        self.stdout.write(self.style.SUCCESS(summary) if not self.failed else self.style.ERROR(summary))
        if self.failed:
            sys.exit(1)

    # ── output helpers ────────────────────────────────────────────────────

    def section(self, title):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(title))

    def verify(self, label, ok, detail="", warn_only=False):
        """warn_only checks describe the data rather than a rule; they are
        reported but never fail the review."""
        if ok:
            self.passed += 1
            self.stdout.write(f"  {self.marks[0]} {label}")
            return
        if warn_only:
            self.passed += 1
            self.stdout.write(self.style.WARNING(f"  ! {label}" + (f": {detail}" if detail else "")))
            return
        self.failed += 1
        self.stdout.write(self.style.ERROR(f"  {self.marks[1]} {label}" + (f": {detail}" if detail else "")))

    @staticmethod
    def differ(first, second):
        return f"{len(first ^ second)} differ" if first != second else ""

    def list(self, students):
        students = list(students)
        if not students:
            return ""
        shown = ", ".join(str(getattr(student, "badge_id", None) or student) for student in students[: self.examples])
        return f"{len(students)} found, e.g. {shown}"

    def visit_list(self, queryset):
        total = queryset.count()
        if not total:
            return ""
        shown = ", ".join(f"{badge} on {day}" for badge, day in queryset.values_list("employee_id__badge_id", "attendance_date")[: self.examples])
        return f"{total} found, e.g. {shown}"
