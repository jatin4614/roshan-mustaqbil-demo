"""Small, reusable RM services built on top of Horilla's stable models."""

import re
from collections import Counter
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from attendance.models import Attendance

# Students enroll in person at the centre, so the day they enroll is their
# first visit: every enrolled student has come at least once.
#
# "Active" means a visit within the last 30 calendar days, today included.
ACTIVE_DAYS = 30
DORMANT_DAYS = 60
ENGAGEMENT_STATUSES = ("Active", "Dormant", "Inactive")
MOVED_ON = "Moved On"
ALL_STATUSES = ENGAGEMENT_STATUSES + (MOVED_ON,)
LAPSED = ("Dormant", "Inactive")
ENGAGEMENT_KEYS = {"Active": "active", "Dormant": "dormant", "Inactive": "inactive", MOVED_ON: "moved"}
# Words staff use; the stored values stay as they are.
ENGAGEMENT_LABELS = {"Active": "Active", "Dormant": "Slipping away", "Inactive": "Inactive", MOVED_ON: "Moved on"}
ENGAGEMENT_HELP = {
    "Active": f"Came in the last {ACTIVE_DAYS} days",
    "Dormant": f"Last came {ACTIVE_DAYS}–{DORMANT_DAYS - 1} days ago",
    "Inactive": f"Hasn't come for {DORMANT_DAYS} days or more",
    MOVED_ON: "Selected, joined a course, moved away or closed",
}
# Students who came only on the day they enrolled. After a week's grace
# they count as not having come back.
NO_RETURN_AFTER_DAYS = 7
NO_RETURN_LABEL = "Didn't come back after enrolling"
NO_RETURN_HELP = f"Enrolled at least {NO_RETURN_AFTER_DAYS} days ago and hasn't been back since"
# The first call list: recent enrollees who haven't come back yet, while a
# call can still make a difference. Older ones are on the Inactive list.
NEW_NO_RETURN_MAX_DAYS = 60
NEW_NO_RETURN_LABEL = "New students who didn't come back"
NEW_NO_RETURN_HELP = f"Enrolled {NO_RETURN_AFTER_DAYS}–{NEW_NO_RETURN_MAX_DAYS} days ago and haven't been back since"
ENROLLMENT_VISIT = "Enrolled at the centre"
REGULAR_VISIT = "Roshan Mustaqbil visit"
AGE_BUCKETS = ((15, "Below 15"), (18, "15–17"), (22, "18–21"), (26, "22–25"), (31, "26–30"), (999, "Above 30"))
# Career goals keep one colour everywhere in the app; the key maps to CSS.
GOAL_ORDER = ("Defence", "UPSC / Civil Services", "NEET UG", "NEET PG", "Other")
GOAL_KEYS = {"Defence": "defence", "UPSC / Civil Services": "upsc", "NEET UG": "neet-ug", "NEET PG": "neet-pg", "Other": "other"}
NOT_RECORDED = "Not recorded"
NO_STATUS = "none"  # filter value for "no follow-up recorded"
NO_VALUE = "__none__"  # filter value for "field left blank"
QUALIFICATIONS = ("Class 10", "Class 12", "Diploma", "Bachelor's Degree", "Postgraduate")
# Calls that didn't reach the student come back to the list after a week.
RETRY_RESULTS = ("Unable to Contact", "Wrong Number")
RETRY_AFTER_DAYS = 7
CALL_BACK_AFTER_DAYS = {"Plans to Return": 14, "Unable to Contact": RETRY_AFTER_DAYS, "Wrong Number": RETRY_AFTER_DAYS}
# Visits needed for a day to count as a day the centre was open.
OPEN_DAY_MIN_VISITS = 5

# Enrollment dates before this are almost certainly typing mistakes.
EARLIEST_ENROLLMENT = date(2015, 1, 1)


# ── Access ───────────────────────────────────────────────────────────────

def is_centre_admin(user):
    """The centre has one sign-in: the administrator, who does everything."""
    return bool(user and user.is_authenticated and user.is_active and user.is_superuser)


# ── Phones ───────────────────────────────────────────────────────────────

def normalize_phone(value):
    """Digits only; drops a +91 / 0 prefix so every number is 10 digits."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def valid_mobile(value):
    return bool(re.fullmatch(r"[6-9]\d{9}", value or ""))


# ── Students and engagement ──────────────────────────────────────────────

def student_queryset():
    """Everyone ever enrolled (and not deleted)."""
    from employee.models import Employee

    return Employee.objects.filter(is_active=True, rm_profile__isnull=False).select_related("rm_profile")


def current_queryset():
    """Enrolled students who haven't moved on: the centre's active base."""
    return student_queryset().filter(rm_profile__outcome="")


def rm_visits():
    return Attendance.objects.filter(employee_id__rm_profile__isnull=False)


def with_last_visit(queryset, today=None):
    """Annotate each student with their latest visit and number of visits.

    The enrollment day always counts as a visit, even if no attendance
    record exists for it (older data), so ``last_visit`` is never earlier
    than the enrollment date and never empty.
    """
    today = today or timezone.localdate()
    latest = (
        Attendance.objects.filter(employee_id=OuterRef("pk"), attendance_date__lte=today)
        .order_by("-attendance_date").values("attendance_date")[:1]
    )
    visits = (
        Attendance.objects.filter(employee_id=OuterRef("pk"), attendance_date__lte=today)
        .order_by().values("employee_id").annotate(total=Count("id")).values("total")
    )
    registered = F("rm_profile__registration_date")
    return queryset.annotate(
        last_visit=Greatest(Coalesce(Subquery(latest), registered), registered),
        visits=Coalesce(Subquery(visits, output_field=IntegerField()), 0),
    )


def engagement_q(status, today=None):
    """Database filter equivalent of ``engagement_status`` for annotated rows."""
    today = today or timezone.localdate()
    active_from = today - timedelta(days=ACTIVE_DAYS - 1)
    dormant_from = today - timedelta(days=DORMANT_DAYS - 1)
    current = Q(rm_profile__outcome="")
    return {
        "Active": current & Q(last_visit__gte=active_from),
        "Dormant": current & Q(last_visit__gte=dormant_from, last_visit__lt=active_from),
        "Inactive": current & (Q(last_visit__lt=dormant_from) | Q(last_visit__isnull=True)),
        MOVED_ON: ~Q(rm_profile__outcome=""),
    }[status]


def no_return_q(today=None):
    """No visit since the day they enrolled, at least a week ago (rows need
    ``last_visit`` from with_last_visit)."""
    today = today or timezone.localdate()
    return Q(
        rm_profile__outcome="", rm_profile__registration_date__lte=today - timedelta(days=NO_RETURN_AFTER_DAYS),
        last_visit__lte=F("rm_profile__registration_date"),
    )


def new_no_return_q(today=None):
    """``no_return_q`` limited to students who enrolled in the last
    NEW_NO_RETURN_MAX_DAYS days: the first call list."""
    today = today or timezone.localdate()
    return no_return_q(today) & Q(rm_profile__registration_date__gte=today - timedelta(days=NEW_NO_RETURN_MAX_DAYS))


def is_no_return(last_visit, registered, status, today=None):
    today = today or timezone.localdate()
    if status == MOVED_ON or not registered or registered > today - timedelta(days=NO_RETURN_AFTER_DAYS):
        return False
    return not last_visit or last_visit <= registered


def is_new_no_return(last_visit, registered, status, today=None):
    today = today or timezone.localdate()
    return is_no_return(last_visit, registered, status, today) and registered >= today - timedelta(days=NEW_NO_RETURN_MAX_DAYS)


def engagement_status(last_visit, today=None, outcome="", registered=None):
    if outcome:
        return MOVED_ON
    # Enrolling is a visit: the last visit is never before the enrollment day.
    last_visit = max(filter(None, (last_visit, registered)), default=None)
    if not last_visit:
        return "Inactive"
    elapsed = ((today or timezone.localdate()) - last_visit).days
    if elapsed < ACTIVE_DAYS:
        return "Active"
    if elapsed < DORMANT_DAYS:
        return "Dormant"
    return "Inactive"


def needs_call_q(today=None):
    """Lapsed students who are due a follow-up call (rows need last_visit)."""
    today = today or timezone.localdate()
    lapsed = engagement_q("Dormant", today) | engagement_q("Inactive", today) | no_return_q(today)
    stale = Q(rm_profile__last_followup_date__isnull=True) | Q(rm_profile__last_followup_date__lt=F("last_visit"))
    retry = Q(rm_profile__current_status__in=RETRY_RESULTS, rm_profile__last_followup_date__lte=today - timedelta(days=RETRY_AFTER_DAYS))
    due = Q(rm_profile__next_call_date__lte=today) | (Q(rm_profile__next_call_date__isnull=True) & (stale | retry))
    return lapsed & due


def needs_call(status, last_visit, profile, today=None):
    """Python twin of needs_call_q for rows already in memory.

    ``profile`` is a mapping with last_followup_date, next_call_date,
    current_status and registration_date.
    """
    today = today or timezone.localdate()
    no_return = is_no_return(last_visit, profile.get("registration_date"), status, today)
    if status not in LAPSED and not no_return:
        return False
    next_call = profile.get("next_call_date")
    if next_call:
        return next_call <= today
    called = profile.get("last_followup_date")
    if not called or (last_visit and called < last_visit):
        return True
    return profile.get("current_status") in RETRY_RESULTS and called <= today - timedelta(days=RETRY_AFTER_DAYS)


def _years_ago(today, years):
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 February
        return today.replace(year=today.year - years, day=28)


def age_q(label, today=None):
    """Database filter for one of the AGE_BUCKETS labels."""
    today = today or timezone.localdate()
    if label == NOT_RECORDED:
        return Q(dob__isnull=True)
    lower = 0
    for upper, bucket in AGE_BUCKETS:
        if bucket == label:
            # age < upper  <=>  born after the day `upper` years ago
            return Q(dob__gt=_years_ago(today, upper), dob__lte=_years_ago(today, lower))
        lower = upper
    return Q()


def age_of(student, today=None):
    if not student.dob:
        return None
    today = today or timezone.localdate()
    return today.year - student.dob.year - ((today.month, today.day) < (student.dob.month, student.dob.day))


def age_group(student, today=None):
    age = age_of(student, today)
    if age is None:
        return NOT_RECORDED
    return next(label for upper, label in AGE_BUCKETS if age < upper)


def engagement_row(student, last_visit, today=None):
    today = today or timezone.localdate()
    registered = student.rm_profile.registration_date
    last_visit = max(filter(None, (last_visit, registered)), default=None)
    status = engagement_status(last_visit, today, student.rm_profile.outcome)
    return {
        "student": student,
        "last_visit": last_visit,
        "status": status,
        "status_key": ENGAGEMENT_KEYS[status],
        "status_label": ENGAGEMENT_LABELS[status],
        "days_since_visit": (today - last_visit).days if last_visit else None,
    }


# ── Attendance ───────────────────────────────────────────────────────────

def mark_student_present(student, day=None, actor=None, note=REGULAR_VISIT):
    """Record one RM visit per student per day.

    ``day`` defaults to today (with the current time). A back-dated visit
    from a paper register has no check-in time. When a student who had
    stopped coming (or had "moved on") checks in again, the stale follow-up
    status is cleared; the call history is kept.
    """
    now = timezone.localtime().replace(tzinfo=None)
    day = day or now.date()
    arrived = now.time().replace(microsecond=0) if day == now.date() else None
    defaults = {
        "attendance_clock_in_date": day,
        "attendance_clock_in": arrived,
        "attendance_worked_hour": "00:00",
        "minimum_hour": "00:00",
        "request_description": note,
    }
    try:
        with transaction.atomic():
            record, created = Attendance.objects.get_or_create(
                employee_id=student, attendance_date=day, defaults=defaults
            )
    except IntegrityError:
        record = Attendance.objects.get(employee_id=student, attendance_date=day)
        created = False
    if created:
        from employee.models import StudentProfile

        profile = StudentProfile.objects.get(employee_id=student.pk)  # never a stale cached copy
        called = profile.last_followup_date
        if (profile.current_status or profile.outcome or profile.next_call_date) and (not called or called <= day):
            profile.current_status = profile.inactivity_reason = profile.outcome = ""
            profile.next_call_date = profile.outcome_date = None
            profile.save(update_fields=["current_status", "inactivity_reason", "outcome", "next_call_date", "outcome_date"])
    return record, created


def record_enrollment_visit(student, day, actor=None):
    """Students enroll in person, so enrolling marks them present that day.

    If they were already marked present that day, that visit becomes the
    enrollment visit.
    """
    record, created = mark_student_present(student, day=day, actor=actor, note=ENROLLMENT_VISIT)
    if record.request_description != ENROLLMENT_VISIT:
        Attendance.objects.filter(pk=record.pk).update(request_description=ENROLLMENT_VISIT)
        record.request_description = ENROLLMENT_VISIT
    return record, created


def move_enrollment_visit(student, new_day):
    """Keep the enrollment visit on the (corrected) enrollment date.

    The old enrollment visit goes: removed if it only stood for the
    enrollment, kept as an ordinary visit if the student really checked in
    that day. A visit already on the new day becomes the enrollment visit.
    Returns how many visits are now dated before the enrollment date.
    """
    old_visits = Attendance.objects.filter(employee_id=student, request_description=ENROLLMENT_VISIT).exclude(attendance_date=new_day)
    for visit in old_visits:
        if visit.attendance_clock_in:
            Attendance.objects.filter(pk=visit.pk).update(request_description=REGULAR_VISIT)
        else:
            visit.delete()
    if new_day <= timezone.localdate():
        existing = Attendance.objects.filter(employee_id=student, attendance_date=new_day).first()
        if existing:
            Attendance.objects.filter(pk=existing.pk).update(request_description=ENROLLMENT_VISIT)
        else:
            Attendance.objects.create(
                employee_id=student, attendance_date=new_day, attendance_clock_in_date=new_day,
                attendance_worked_hour="00:00", minimum_hour="00:00", request_description=ENROLLMENT_VISIT,
            )
    return Attendance.objects.filter(employee_id=student, attendance_date__lt=new_day).count()


def delete_students(ids):
    """Remove students completely: visits, profile and calls.

    Returns (students, visits) removed. A student the HR side still
    protects is switched off instead, which hides them everywhere.
    """
    from django.db.models import ProtectedError

    from attendance.models import AttendanceActivity, AttendanceLateComeEarlyOut
    from employee.models import Employee, StudentProfile

    from django.apps import apps

    ids = list(ids)
    if apps.is_installed("payroll"):
        # Contracts the HR side once made for form-enrolled students.
        apps.get_model("payroll", "Contract").objects.entire().filter(employee_id__in=ids).delete()
    visits = Attendance.objects.filter(employee_id__in=ids)
    removed = visits.count()
    AttendanceLateComeEarlyOut.objects.filter(attendance_id__in=visits).delete()
    AttendanceActivity.objects.filter(employee_id__in=ids).delete()
    visits.delete()  # per-row delete signals also clear work records
    StudentProfile.objects.filter(employee_id__in=ids).delete()  # calls go with them
    try:
        Employee.objects.filter(id__in=ids).delete()
    except ProtectedError:
        for student_id in ids:
            try:
                Employee.objects.filter(id=student_id).delete()
            except ProtectedError:
                # Kept for the HR record that protects it, but out of the
                # way: its email and registration number are free again.
                Employee.objects.filter(id=student_id).update(is_active=False, badge_id=None, email=f"removed-{student_id}@rm.removed")
    return len(ids), removed


def visit_summary(ids=None):
    """Per student: their visit dates, oldest first."""
    queryset = rm_visits()
    if ids is not None:
        queryset = queryset.filter(employee_id__in=ids)
    days = {}
    for student, day in queryset.order_by("employee_id", "attendance_date").values_list("employee_id", "attendance_date"):
        days.setdefault(student, []).append(day)
    return days


# ── Follow-up calls ──────────────────────────────────────────────────────

def record_followup(profile, *, result, called_on=None, reason="", notes="", next_call_date=None, user=None):
    """Log a follow-up call and update the student's latest status.

    Results that mean the student has moved on (selected, joined a course,
    moved away, no longer interested) give the student an outcome, which
    takes them out of the active base until they come back.
    """
    from employee.models import StudentFollowUp, StudentProfile

    called_on = called_on or timezone.localdate()
    if not next_call_date and result in CALL_BACK_AFTER_DAYS:
        next_call_date = called_on + timedelta(days=CALL_BACK_AFTER_DAYS[result])
    entry = StudentFollowUp.objects.create(
        student=profile, called_on=called_on, result=result, reason=reason, notes=notes,
        next_call_date=next_call_date, created_by=user if user and user.is_authenticated else None,
    )
    latest = profile.followups.order_by("-called_on", "-created_at").first()
    if latest.pk == entry.pk:
        profile.current_status = result
        profile.last_followup_date = called_on
        profile.inactivity_reason = reason or profile.inactivity_reason
        profile.followup_notes = notes
        profile.next_call_date = next_call_date
        outcome = StudentProfile.STATUS_OUTCOMES.get(result, "")
        if outcome:
            profile.outcome, profile.outcome_date = outcome, called_on
        profile.save(update_fields=["current_status", "last_followup_date", "inactivity_reason", "followup_notes", "next_call_date", "outcome", "outcome_date"])
    return entry


# ── Small helpers ────────────────────────────────────────────────────────

def goal_label(student):
    return student.rm_profile.career_goal or NOT_RECORDED


def goal_key(goal):
    return GOAL_KEYS.get(goal, "none")


def requirement_counts(students):
    counts = Counter()
    for student in students:
        counts.update(student.rm_profile.requirements or [])
    return counts


def initials(student):
    first = (student.employee_first_name or "").strip()[:1]
    last = (student.employee_last_name or "").strip()[:1]
    return (first + last).upper() or "?"


def target_label(profile):
    """The specific exam: Defence entry, target exam or the goal itself."""
    if profile.career_goal == "Defence":
        return profile.defence_entry or ""
    if profile.target_exam == "Other":
        return profile.goal_detail or "Other"
    return profile.target_exam or (profile.goal_detail if profile.career_goal == "Other" else "")


def normalize_qualification(value):
    """Map free-text qualifications ("12th", "B.Sc") onto QUALIFICATIONS."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    if re.search(r"post|master|\bm\.?\s?(a|sc|com|tech)\b|mba|mca", text):
        return "Postgraduate"
    if re.search(r"bachelor|graduat|\bb\.?\s?(a|sc|com|tech|e)\b|mbbs|bds|degree", text):
        return "Bachelor's Degree"
    if "diploma" in text or "polytechnic" in text or re.search(r"\biti\b", text):
        return "Diploma"
    if re.search(r"\b12|xii|higher secondary|hsc|intermediate", text):
        return "Class 12"
    if re.search(r"\b10|\bx\b|matric|ssc", text):
        return "Class 10"
    return value.strip()
