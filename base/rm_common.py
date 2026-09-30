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
PROFILE_FIELDS = (
    "career_goal", "defence_entry", "target_exam", "goal_detail", "locality",
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


def stay_summary(start, end):
    """Time in the centre over a date range (today excluded: people are
    still in). Returns the typical stay, the bucket counts and how many
    visits had a check-out."""
    from base.rm import STAY_BUCKETS, minutes_between, stay_bucket

    rows = rm_visits().filter(attendance_date__range=(start, end), attendance_clock_in__isnull=False).values_list(
        "attendance_date", "attendance_clock_in", "attendance_clock_out", "employee_id__rm_profile__career_goal",
    )
    stays, by_goal, timed = [], {}, 0
    for day, arrived, left, goal in rows:
        timed += 1
        minutes = minutes_between(day, arrived, left)
        if minutes is not None:
            stays.append(minutes)
            by_goal.setdefault(goal or "", []).append(minutes)
    buckets = Counter(stay_bucket(minutes) for minutes in stays)
    return {
        "median": median(stays), "count": len(stays), "timed": timed,
        "buckets": {label: buckets.get(label, 0) for _, label in STAY_BUCKETS},
        "by_goal": {goal: median(values) for goal, values in by_goal.items()},
    }


def median(values):
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else round((ordered[middle - 1] + ordered[middle]) / 2)


def occupancy_by_hour(days, first_hour=9, last_hour=18):
    """Average number of students in the centre during each hour, over the
    given open days, from visits with both a check-in and a check-out. A
    student counts for an hour if they were in at half past."""
    from datetime import time as clock

    counts = Counter()
    for arrived, left in rm_visits().filter(attendance_date__in=days, attendance_clock_in__isnull=False, attendance_clock_out__isnull=False).values_list("attendance_clock_in", "attendance_clock_out"):
        for hour in range(first_hour, last_hour):
            if arrived <= clock(hour, 30) < left:
                counts[hour] += 1
    return {hour: round(counts[hour] / len(days), 1) if days else 0 for hour in range(first_hour, last_hour)}


def occupancy_today(day, now, first_hour=9):
    """How many were in the centre at half past each hour today, so far."""
    from datetime import time as clock

    visits = list(rm_visits().filter(attendance_date=day, attendance_clock_in__isnull=False).values_list("attendance_clock_in", "attendance_clock_out"))
    points = {}
    for hour in range(first_hour, 18):
        moment = clock(hour, 30)
        if moment > now:
            break
        points[hour] = sum(1 for arrived, left in visits if arrived <= moment and (left is None or left > moment))
    return points


def hour_label(hour):
    return f"{hour % 12 or 12} {'am' if hour < 12 else 'pm'}"


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
