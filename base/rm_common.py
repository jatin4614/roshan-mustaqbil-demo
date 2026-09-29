"""Helpers shared by the Roshan Mustaqbil screens (base.rm_* views)."""

import csv
from collections import Counter
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Count
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from base.rm import (
    AGE_BUCKETS, ENGAGEMENT_KEYS, ENGAGEMENT_LABELS, ENROLLMENT_VISIT, GOAL_KEYS, NO_RETURN_AFTER_DAYS, NO_VALUE,
    NOT_RECORDED, OPEN_DAY_MIN_VISITS, engagement_status, initials, is_no_return, rm_visits, student_queryset,
    target_label, with_last_visit,
)
from employee.models import Employee, StudentProfile

PAGE_SIZE = 50
GENDER_LABELS = {value: str(label) for value, label in Employee.choice_gender}
STATUS_LABELS = dict(StudentProfile.CURRENT_STATUSES)
OUTCOME_LABELS = dict(StudentProfile.OUTCOMES)
PURPOSE_LABELS = dict(StudentProfile.PURPOSES)
PREP_LABELS = dict(StudentProfile.PREP_STAGES)
PROFILE_FIELDS = (
    "career_goal", "defence_entry", "target_exam", "goal_detail", "prep_stage", "target_year", "locality",
    "current_status", "last_followup_date", "next_call_date", "outcome", "outcome_date", "purpose_of_rm",
    "requirements", "registration_date", "expectations",
)


def today_label(day):
    return day.strftime("%A, %d %B %Y").replace(" 0", " ")


def students_url(**params):
    query = urlencode({key: value for key, value in params.items() if value})
    return reverse("rm-students") + (f"?{query}" if query else "")


def goal_url(goal):
    if goal in GOAL_KEYS:
        return students_url(goal=goal)
    return students_url(goal=NO_VALUE) if goal == NOT_RECORDED else ""


def status_url(status):
    return students_url(engagement=status)


def student_values(today, queryset=None):
    """One lightweight dict per student, with engagement worked out."""
    queryset = queryset if queryset is not None else student_queryset()
    rows = list(with_last_visit(queryset, today).values(
        "id", "employee_first_name", "employee_last_name", "badge_id", "phone", "gender", "dob", "qualification",
        "last_visit", "visits", *(f"rm_profile__{field}" for field in PROFILE_FIELDS),
    ))
    for row in rows:
        for field in PROFILE_FIELDS:
            row[field] = row.pop(f"rm_profile__{field}")
        row["status"] = engagement_status(row["last_visit"], today, row["outcome"], row["registration_date"])
        row["no_return"] = is_no_return(row["last_visit"], row["registration_date"], row["status"], today)
        row["came_back"] = bool(row["last_visit"] and row["registration_date"] and row["last_visit"] > row["registration_date"])
        # Enrolled less than a week ago and not back yet: too early to say.
        row["too_early"] = bool(not row["came_back"] and row["registration_date"] and (today - row["registration_date"]).days < NO_RETURN_AFTER_DAYS)
        row["name"] = f"{row['employee_first_name']} {row['employee_last_name'] or ''}".strip()
        row["goal"] = row["career_goal"] or NOT_RECORDED
    return rows


def age_label(dob, today):
    if not dob:
        return NOT_RECORDED
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return next(label for upper, label in AGE_BUCKETS if age < upper)


def visits_per_day(start, end):
    return dict(
        rm_visits().filter(attendance_date__range=(start, end)).order_by()
        .values("attendance_date").annotate(total=Count("id")).values_list("attendance_date", "total")
    )


def is_open(count):
    """A day counts as open when enough students came (stray marks don't)."""
    return count >= OPEN_DAY_MIN_VISITS


def typical_by_now(today, now=None, weeks=4):
    """Average check-ins by this time of day on recent open days.

    Only check-ins with a time count (visits entered later from a paper
    register have none), so after closing time this is the average open
    day's check-ins.
    """
    now = now or timezone.localtime().time()
    start = today - timedelta(days=weeks * 7)
    timed = rm_visits().filter(attendance_date__range=(start, today - timedelta(days=1)), attendance_clock_in__isnull=False)
    per_day = Counter(timed.values_list("attendance_date", flat=True))
    open_days = [day for day, count in per_day.items() if is_open(count)]
    if not open_days:
        return None
    by_now = timed.filter(attendance_date__in=open_days, attendance_clock_in__lte=now).count()
    return round(by_now / len(open_days))


def day_checkins(day, limit=None):
    visits = rm_visits().filter(attendance_date=day).select_related("employee_id", "employee_id__rm_profile").order_by("-attendance_clock_in", "-id")
    return visits[:limit] if limit else visits


def checkin_rows(visits):
    return [
        {
            "record": visit, "student": visit.employee_id, "initials": initials(visit.employee_id),
            "goal": visit.employee_id.rm_profile.career_goal,
            "goal_key": GOAL_KEYS.get(visit.employee_id.rm_profile.career_goal, "none"),
            "is_enrollment": visit.request_description == ENROLLMENT_VISIT,
        }
        for visit in visits
    ]


def status_pill(status):
    return {"key": ENGAGEMENT_KEYS[status], "label": ENGAGEMENT_LABELS[status]}


def csv_response(filename, header):
    """A CSV download that Excel on Windows opens with the right characters."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(header)
    return response, writer


def describe_target(profile):
    return target_label(profile)
