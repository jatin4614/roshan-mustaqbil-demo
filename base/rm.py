"""Small, reusable RM services built on top of Horilla's stable models."""

from collections import Counter
from datetime import date, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from attendance.models import Attendance

ACTIVE_DAYS = 30
DORMANT_DAYS = 60
ENGAGEMENT_STATUSES = ("Active", "Dormant", "Inactive", "Never Attended")
AGE_BUCKETS = ((15, "Below 15"), (18, "15–17"), (22, "18–21"), (26, "22–25"), (31, "26–30"), (999, "Above 30"))


def student_queryset():
    from employee.models import Employee

    return Employee.objects.filter(is_active=True, rm_profile__isnull=False).select_related("rm_profile")


def age_group(student, today=None):
    if not student.dob:
        return "Not recorded"
    today = today or date.today()
    age = today.year - student.dob.year - ((today.month, today.day) < (student.dob.month, student.dob.day))
    return next(label for upper, label in AGE_BUCKETS if age < upper)


def attendance_summary(students=None, today=None):
    today = today or date.today()
    students = list(students if students is not None else student_queryset())
    ids = [student.id for student in students]
    last_visits = dict(
        Attendance.objects.filter(employee_id_id__in=ids, attendance_date__lte=today)
        .values("employee_id_id").annotate(last=Max("attendance_date"))
        .values_list("employee_id_id", "last")
    )
    return last_visits


def engagement_status(last_visit, today=None):
    if not last_visit:
        return "Never Attended"
    elapsed = ((today or date.today()) - last_visit).days
    if elapsed <= ACTIVE_DAYS:
        return "Active"
    if elapsed <= DORMANT_DAYS:
        return "Dormant"
    return "Inactive"


def engagement_for_students(students=None, today=None):
    today = today or date.today()
    students = list(students if students is not None else student_queryset())
    last_visits = attendance_summary(students, today)
    rows = []
    for student in students:
        last_visit = last_visits.get(student.id)
        rows.append({
            "student": student,
            "last_visit": last_visit,
            "status": engagement_status(last_visit, today),
            "days_since_visit": (today - last_visit).days if last_visit else None,
        })
    return rows


def mark_student_present(student, when=None, actor=None):
    """Create today's RM visit once; no HR-facing timing workflow is exposed."""
    when = when or timezone.localtime().replace(tzinfo=None)
    visit_date = when.date()
    defaults = {
        "attendance_clock_in_date": visit_date,
        "attendance_clock_in": when.time().replace(microsecond=0),
        "attendance_worked_hour": "00:00",
        "minimum_hour": "00:00",
        "request_description": "Roshan Mustaqbil visit",
    }
    try:
        with transaction.atomic():
            record, created = Attendance.objects.get_or_create(
                employee_id=student, attendance_date=visit_date, defaults=defaults
            )
    except IntegrityError:
        record = Attendance.objects.get(employee_id=student, attendance_date=visit_date)
        created = False
    return record, created


def goal_label(student):
    return student.rm_profile.career_goal or "Not specified"


def requirement_counts(students):
    counts = Counter()
    for student in students:
        counts.update(student.rm_profile.requirements or [])
    return counts
