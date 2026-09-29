"""Automated review of the Roshan Mustaqbil data and screens.

Checks the rules the app depends on (students enroll in person, so the
enrollment day is a visit; "didn't come back" is computed the same way in
Python and in the database; the call queues don't overlap) plus basic data
quality, and that removed wording hasn't crept back into the templates.

    python manage.py review_rm

Exits with status 1 if any check fails, so it can run in CI or before a demo.
"""

import re
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, F, Max, Min, Q
from django.utils import timezone

from base.rm import (
    ENGAGEMENT_LABELS, ENROLLMENT_VISIT, MOVED_ON, NO_RETURN_AFTER_DAYS, engagement_status, no_return_q,
    normalize_phone, rm_visits, student_queryset, valid_mobile, with_last_visit,
)
from employee.models import StudentProfile


class Command(BaseCommand):
    help = "Check Roshan Mustaqbil data invariants, call queues, data quality and templates."

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
        visits = rm_visits()

        self.section("Model invariants")
        per_student = dict(visits.order_by().values("employee_id").annotate(total=Count("id")).values_list("employee_id", "total"))
        no_visits = [student for student in student_queryset().select_related(None).only("id", "badge_id") if student.id not in per_student]
        self.verify("Every student has at least one visit", not no_visits, self.list(no_visits))
        early = visits.filter(attendance_date__lt=F("employee_id__rm_profile__registration_date"))
        self.verify("No visit is dated before the student enrolled", not early.exists(), self.visit_list(early), warn_only=True)
        future = visits.filter(attendance_date__gt=today)
        self.verify("No visit is dated in the future", not future.exists(), self.visit_list(future))
        with_login = student_queryset().filter(employee_user_id__isnull=False, employee_user_id__is_active=True)
        self.verify("No student has an active login (students are records, not users)", not with_login.exists(), self.list(with_login))

        self.section("Enrollment visit (students enroll in person)")
        enrollment = visits.filter(request_description=ENROLLMENT_VISIT)
        per_enrollment = Counter(enrollment.values_list("employee_id", flat=True))
        profiles = dict(StudentProfile.objects.values_list("employee_id", "registration_date"))
        missing = [student_id for student_id in profiles if per_enrollment[student_id] == 0]
        duplicated = [student_id for student_id, total in per_enrollment.items() if total > 1]
        self.verify("Every student has exactly one enrollment visit", not missing and not duplicated,
                   f"{len(missing)} without one, {len(duplicated)} with several" if missing or duplicated else "")
        misdated = [
            student_id for student_id, day in enrollment.values_list("employee_id", "attendance_date")
            if profiles.get(student_id) and day != profiles[student_id]
        ]
        self.verify("The enrollment visit is on the enrollment date", not misdated, f"{len(misdated)} on another date" if misdated else "")

        self.section("Didn't come back after enrolling")
        cutoff = today - timedelta(days=NO_RETURN_AFTER_DAYS)
        by_rule = {
            student.id for student in students
            if not student.rm_profile.outcome and student.rm_profile.registration_date <= cutoff
            and student.last_visit <= student.rm_profile.registration_date
        }
        by_query = set(students.filter(no_return_q(today)).values_list("id", flat=True))
        self.verify(f"Python rule and database query agree ({len(by_rule)} students)", by_rule == by_query,
                   f"{len(by_rule ^ by_query)} differ" if by_rule != by_query else "")

        self.section("Engagement")
        statuses = Counter(
            engagement_status(student.last_visit, today, student.rm_profile.outcome, student.rm_profile.registration_date)
            for student in students
        )
        legacy = StudentProfile.objects.filter(Q(current_status__iexact="Never Attended") | Q(current_status__iexact="Never came"))
        self.verify("No follow-up status uses the removed \"Never came\" value", not legacy.exists(), f"{legacy.count()} records" if legacy.exists() else "")
        self.verify("Some students are slipping away and some inactive (data looks realistic)", statuses["Dormant"] > 0 and statuses["Inactive"] > 0,
                   f"slipping away {statuses['Dormant']}, inactive {statuses['Inactive']}", warn_only=True)

        self.section("Call queues")
        from base.rm_students import QUEUES, _queue_students

        queues = {key: {student.id for student in _queue_students(key, today)} for key, _, _ in QUEUES}
        self.verify(f"\"Didn't come back after enrolling\" queue has students ({len(queues['once'])})", bool(queues["once"]), warn_only=True)
        overlaps = [
            f"{first}/{second}: {len(queues[first] & queues[second])}"
            for index, first in enumerate(queues) for second in list(queues)[index + 1:]
            if queues[first] & queues[second]
        ]
        self.verify("No student is in two call queues", not overlaps, ", ".join(overlaps))
        moved_in_queue = set().union(*queues.values()) & set(students.filter(~Q(rm_profile__outcome="")).values_list("id", flat=True))
        self.verify("Moved-on students are never in a call queue", not moved_in_queue, f"{len(moved_in_queue)} students" if moved_in_queue else "")

        self.section("Data quality")
        undated = StudentProfile.objects.filter(registration_date__isnull=True)
        self.verify("Every student has an enrollment date", not undated.exists(), f"{undated.count()} without" if undated.exists() else "")
        bad_phones = [student for student in student_queryset().select_related(None).only("id", "badge_id", "phone") if not valid_mobile(normalize_phone(student.phone))]
        self.verify("Every phone number is a 10-digit mobile number", not bad_phones, self.list(bad_phones))
        shared = [phone for phone, total in Counter(student_queryset().values_list("phone", flat=True)).items() if total > 1]
        self.verify(f"Shared phone numbers are few ({len(shared)}; siblings often share)", len(shared) <= max(20, len(profiles) // 20), warn_only=True)

        self.section("Templates and styles")
        template_dir = Path(settings.BASE_DIR) / "templates" / "rm"
        texts = {path: path.read_text(encoding="utf-8") for path in template_dir.rglob("*.html")}
        hits = [path.name for path, text in texts.items() if "Never Attended" in text]
        self.verify('"Never Attended" appears in no template', not hits, ", ".join(hits))
        # "never came back after enrolling" is correct wording; the removed
        # status label "Never came" is not.
        hits = [path.name for path, text in texts.items() if re.search(r"never came(?! back)", text, re.IGNORECASE)]
        self.verify('The removed "Never came" status appears in no template', not hits, ", ".join(hits))
        css = (Path(settings.BASE_DIR) / "static" / "rm" / "rm.css").read_text(encoding="utf-8")
        self.verify("rm.css has no .k-never rule", ".k-never" not in css)

        self.section("Students by status")
        no_return = len(by_query)
        rows = [(ENGAGEMENT_LABELS[status], statuses[status]) for status in ("Active", "Dormant", "Inactive", MOVED_ON)]
        rows.append(("Total enrolled", sum(statuses.values())))
        width = max(len(label) for label, _ in rows)
        for label, total in rows:
            self.stdout.write(f"  {label.ljust(width)}  {total:>5}")
        self.stdout.write(f"  Didn't come back after enrolling (across the statuses above): {no_return}")

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
