"""Roshan Mustaqbil dashboards: the centre overview, attendance patterns,
career goals and analytics. Student, attendance-desk, staff and import
screens live in base.rm_students, base.rm_attendance, base.rm_staff and
base.rm_import.
"""

from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from base import rm_charts as charts
from base.rm import (
    ACTIVE_DAYS, AGE_BUCKETS, ALL_STATUSES, ENGAGEMENT_HELP, ENGAGEMENT_KEYS, ENGAGEMENT_LABELS,
    ENGAGEMENT_STATUSES, GOAL_KEYS, GOAL_ORDER, MOVED_ON, NO_STATUS, NO_VALUE, NOT_RECORDED,
    QUALIFICATIONS, first_visits, needs_call, rm_visits,
)
from base.rm_access import rm_required
from base.rm_common import (
    OUTCOME_LABELS, PREP_LABELS, PURPOSE_LABELS, STATUS_LABELS, age_label, checkin_rows,
    day_checkins, goal_url, is_open, status_url, student_values, students_url, today_label,
    typical_by_now, visits_per_day,
)
from employee.models import StudentFollowUp, StudentProfile

NOT_CONTACTED = "Not contacted yet"
# What happened to students who stopped coming: action first, then what
# they told us, then the students who have moved on for good.
AFTERMATH = (
    (NOT_CONTACTED, "call"),
    ("Unable to Contact", "muted"), ("Wrong Number", "muted"),
    ("Plans to Return", "neutral"), ("Preparing from Home", "neutral"), ("Studying at School / College", "neutral"),
    ("Preparing at Another Institute", "neutral"), ("Employed", "neutral"), ("Other", "neutral"),
    ("Selected", "good"), ("Joined Professional Course", "good"), ("Moved Away", "lost"), ("Closed", "lost"),
)


def _engagement_block(rows, include_moved=True):
    counts = Counter(row["status"] for row in rows)
    current = sum(counts[status] for status in ENGAGEMENT_STATUSES)
    block = []
    for status in (ALL_STATUSES if include_moved else ENGAGEMENT_STATUSES):
        denominator = len(rows) if status == MOVED_ON else current
        block.append({
            "status": status, "label": ENGAGEMENT_LABELS[status], "key": ENGAGEMENT_KEYS[status], "count": counts[status],
            "share": charts.share_label(counts[status], denominator), "help": ENGAGEMENT_HELP[status], "url": status_url(status),
        })
    return block


def _active_trend(today, weeks=26):
    """Students active (visited in the previous 30 days) at each week's end."""
    start = today - timedelta(days=7 * (weeks - 1) + ACTIVE_DAYS - 1)
    by_day = defaultdict(set)
    for student, day in rm_visits().filter(attendance_date__range=(start, today)).values_list("employee_id", "attendance_date"):
        by_day[day].add(student)
    points = []
    for weeks_back in range(weeks - 1, -1, -1):
        end = today - timedelta(weeks=weeks_back)
        seen = set()
        for offset in range(ACTIVE_DAYS):
            seen |= by_day.get(end - timedelta(days=offset), set())
        first_of_month = end.day <= 7
        points.append({
            "label": end.strftime("%b") if first_of_month and weeks_back else ("Now" if not weeks_back else ""),
            "tip": "Today" if not weeks_back else f"Week ending {end.strftime('%a %d %b').replace(' 0', ' ')}",
            "value": len(seen),
        })
    return points


def _distinct_visitors(start, end):
    return rm_visits().filter(attendance_date__range=(start, end)).values("employee_id").distinct().count()


def regulars_missing(today, rows_by_id=None):
    """Early warning: came at least 3 times in the three weeks before last
    week, then not at all in the last 7 days, and nobody has called yet."""
    earlier = Counter(rm_visits().filter(attendance_date__range=(today - timedelta(days=27), today - timedelta(days=7))).values_list("employee_id", flat=True))
    recent = set(rm_visits().filter(attendance_date__range=(today - timedelta(days=6), today)).values_list("employee_id", flat=True))
    called = set(StudentFollowUp.objects.filter(called_on__gte=today - timedelta(days=6)).values_list("student__employee_id", flat=True))
    missing = [(student, visits) for student, visits in earlier.items() if visits >= 3 and student not in recent and student not in called]
    if rows_by_id is not None:
        missing = [(student, visits) for student, visits in missing if student in rows_by_id and rows_by_id[student]["status"] == "Active"]
    return sorted(missing, key=lambda item: -item[1])


def aftermath_bars(rows):
    """What happened to students who stopped coming (or never came)."""
    counts = Counter()
    for row in rows:
        if row["status"] == MOVED_ON:
            counts[row["outcome"]] += 1
        elif row["status"] in {"Inactive", "Never Attended"}:
            stale = row["last_followup_date"] and row["last_visit"] and row["last_followup_date"] < row["last_visit"]
            counts[NOT_CONTACTED if not row["current_status"] or stale else row["current_status"]] += 1
    total = sum(counts.values())
    labels = {**STATUS_LABELS, **OUTCOME_LABELS, "Selected": "Selected (armed forces / service)", NOT_CONTACTED: NOT_CONTACTED}
    inactive_url = reverse("rm-inactive-students")

    def link(bucket):
        if bucket == NOT_CONTACTED:
            return f"{inactive_url}?current_status={NO_STATUS}"
        if bucket in OUTCOME_LABELS:
            return students_url(engagement=MOVED_ON, outcome=bucket)
        return f"{inactive_url}?current_status={bucket}"

    order = [bucket for bucket, _ in AFTERMATH]
    keys = dict(AFTERMATH)
    return charts.bars({bucket: count for bucket, count in counts.items() if count}, total=total, order=order, keys=keys, url=link, labels=labels), total


@rm_required("frontdesk")
def rm_dashboard(request):
    today = timezone.localdate()
    rows = student_values(today)
    rows_by_id = {row["id"]: row for row in rows}
    current = [row for row in rows if row["status"] != MOVED_ON]
    engagement = _engagement_block(rows)
    active = engagement[0]["count"]
    active_then = _distinct_visitors(today - timedelta(days=2 * ACTIVE_DAYS - 1), today - timedelta(days=ACTIVE_DAYS))

    # Present today, compared with a typical day at this time.
    today_count = rm_visits().filter(attendance_date=today).count()
    typical = typical_by_now(today)

    # How often active students come.
    per_student = Counter(rm_visits().filter(attendance_date__range=(today - timedelta(days=ACTIVE_DAYS - 1), today)).values_list("employee_id", flat=True))
    rare = sum(1 for visits in per_student.values() if visits <= 2)

    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    enrolled_month = [row for row in rows if row["registration_date"] and row["registration_date"] >= month_start]
    enrolled_last_month = sum(1 for row in rows if row["registration_date"] and last_month_start <= row["registration_date"] < month_start)

    due = [row for row in current if needs_call(row["status"], row["last_visit"], row, today)]
    due_by_status = Counter(row["status"] for row in due)
    missing = regulars_missing(today, rows_by_id)
    calls_week = StudentFollowUp.objects.filter(called_on__gte=today - timedelta(days=6)).count()
    moved = Counter(row["outcome"] for row in rows if row["status"] == MOVED_ON)
    aftermath, aftermath_total = aftermath_bars(rows)

    context = {
        "today": today, "today_label": today_label(today), "total": len(rows), "current_total": len(current),
        "active": active, "active_change": active - active_then, "engagement": engagement,
        "moved": {"total": sum(moved.values()), "selected": moved.get("Selected", 0)},
        "trend": charts.line(_active_trend(today)),
        "kpis": {
            "today": today_count, "typical": typical,
            "median_visits": charts.median(per_student.values()), "rare": rare, "active_visitors": len(per_student),
            "enrolled_month": len(enrolled_month), "enrolled_month_came": sum(1 for row in enrolled_month if row["last_visit"]),
            "enrolled_last_month": enrolled_last_month,
            "due": len(due), "due_dormant": due_by_status["Dormant"],
        },
        "queues": [
            {"label": "Regulars who missed this week", "help": "Came 3+ times in the weeks before, not in the last 7 days", "count": len(missing), "url": reverse("rm-calls") + "?queue=missing"},
            {"label": "Slipping away", "help": ENGAGEMENT_HELP["Dormant"], "count": due_by_status["Dormant"], "url": reverse("rm-calls") + "?queue=Dormant"},
            {"label": "Inactive", "help": ENGAGEMENT_HELP["Inactive"], "count": due_by_status["Inactive"], "url": reverse("rm-calls") + "?queue=Inactive"},
            {"label": "Never came", "help": ENGAGEMENT_HELP["Never Attended"], "count": due_by_status["Never Attended"], "url": reverse("rm-calls") + "?queue=Never+Attended"},
        ],
        "calls_week": calls_week,
        "checkins": checkin_rows(day_checkins(today, 6)),
        "goals": charts.bars(Counter(row["goal"] for row in current), total=len(current), order=GOAL_ORDER + (NOT_RECORDED,), keys={**GOAL_KEYS, NOT_RECORDED: "muted"}, url=goal_url),
        "aftermath": aftermath, "aftermath_total": aftermath_total,
    }
    return render(request, "rm/dashboard.html", context)


@rm_required("coordinator")
def attendance_dashboard(request):
    today = timezone.localdate()
    days = int(request.GET.get("days", 30)) if request.GET.get("days") in {"30", "60", "90"} else 30
    start = today - timedelta(days=days - 1)
    per_day = visits_per_day(start, today)
    open_days = [day for day, count in per_day.items() if is_open(count) and day != today]
    average = round(sum(per_day[day] for day in open_days) / len(open_days), 1) if open_days else 0
    step = 7 if days > 45 else 5
    points = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        edge = offset == 0 or offset == days - 1 or (days - 1 - offset) % step == 0
        count = per_day.get(day, 0)
        points.append({
            "label": day.strftime("%d %b").lstrip("0") if edge else "",
            "tip": ("Today, so far: " if day == today else "") + day.strftime("%a %d %b").replace(" 0", " "),
            "value": count, "closed": not is_open(count) and day != today,
        })
    visits = rm_visits().filter(attendance_date__range=(start, today))
    week = rm_visits().filter(attendance_date__range=(today - timedelta(days=6), today))
    week_students = set(week.values_list("employee_id", flat=True))
    firsts = first_visits(week_students)
    new_this_week = sum(1 for day in firsts.values() if day >= today - timedelta(days=6))

    weekday_totals, weekday_days = Counter(), Counter()
    for day in open_days:
        weekday_totals[day.weekday()] += per_day[day]
        weekday_days[day.weekday()] += 1
    names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    full_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    weekday_points = [
        {"label": name, "tip": f"Average {full}", "value": round(weekday_totals[index] / weekday_days[index], 1) if weekday_days[index] else 0}
        for index, (name, full) in enumerate(zip(names, full_names))
    ]
    hours = Counter(time.hour for time in visits.filter(attendance_date__in=open_days).values_list("attendance_clock_in", flat=True) if time)
    first, last = min(list(hours) + [9]), max(list(hours) + [17])

    def hour_label(hour):
        return f"{hour % 12 or 12} {'am' if hour < 12 else 'pm'}"

    hour_points = [
        {"label": hour_label(hour) if (hour - first) % 2 == 0 else "", "tip": f"{hour_label(hour)} to {hour_label(hour + 1)}",
         "value": round(hours.get(hour, 0) / len(open_days), 1) if open_days else 0}
        for hour in range(first, last + 1)
    ]
    per_student = Counter(visits.values_list("employee_id", flat=True))
    regulars = (
        visits.values("employee_id", "employee_id__employee_first_name", "employee_id__employee_last_name", "employee_id__badge_id", "employee_id__rm_profile__career_goal")
        .annotate(total=Count("id")).order_by("-total", "employee_id__employee_first_name")[:8]
    )
    regular_rows = [
        {
            "id": row["employee_id"], "name": f"{row['employee_id__employee_first_name']} {row['employee_id__employee_last_name'] or ''}".strip(),
            "badge": row["employee_id__badge_id"], "total": row["total"], "goal_key": GOAL_KEYS.get(row["employee_id__rm_profile__career_goal"], "none"),
            "initials": ((row["employee_id__employee_first_name"] or "")[:1] + (row["employee_id__employee_last_name"] or "")[:1]).upper(),
            "width": min(100, round(row["total"] / max(len(open_days) + 1, 1) * 100)),
        }
        for row in regulars
    ]
    # Visits per active student for each goal: which groups use the centre
    # most, independent of how many students each goal has.
    goal_of = dict(visits.values_list("employee_id", "employee_id__rm_profile__career_goal").distinct())
    goal_visits, goal_students = Counter(), Counter()
    for student, count in per_student.items():
        goal = goal_of.get(student) or NOT_RECORDED
        goal_visits[goal] += count
        goal_students[goal] += 1
    intensity = {goal: round(goal_visits[goal] / goal_students[goal], 1) for goal in goal_students}
    peak = max(intensity.values(), default=0)
    goal_rows = [
        {"label": goal, "count": intensity[goal], "share": f"{goal_students[goal]} students", "width": round(intensity[goal] / peak * 100) if peak else 0,
         "key": GOAL_KEYS.get(goal, "muted"), "url": goal_url(goal)}
        for goal in GOAL_ORDER + (NOT_RECORDED,) if goal in intensity
    ]
    context = {
        "today": today, "today_label": today_label(today), "days": days, "ranges": (30, 60, 90),
        "kpis": {
            "today": per_day.get(today, 0), "typical": typical_by_now(today),
            "week_unique": len(week_students), "new_this_week": new_this_week,
            "range_unique": len(per_student), "range_visits": visits.count(), "open_days": len(open_days),
            "median": charts.median(per_student.values()),
        },
        "daily": charts.columns(points, highlight_last=True, average=average),
        "weekday": charts.columns(weekday_points, unit="visit"),
        "hours": charts.columns(hour_points, unit="check-in"),
        "checkins": checkin_rows(day_checkins(today)),
        "regulars": regular_rows,
        "goal_intensity": goal_rows,
    }
    return render(request, "rm/attendance_dashboard.html", context)


@rm_required("coordinator")
def career_goals(request):
    today = timezone.localdate()
    rows = [row for row in student_values(today) if row["status"] != MOVED_ON]
    total = len(rows)
    by_goal = defaultdict(list)
    for row in rows:
        by_goal[row["goal"]].append(row)
    goals = [goal for goal in GOAL_ORDER + (NOT_RECORDED,) if goal in by_goal or goal != NOT_RECORDED]
    cards = []
    for goal in goals:
        members = by_goal.get(goal, [])
        statuses = Counter(row["status"] for row in members)
        cards.append({
            "label": goal, "key": GOAL_KEYS.get(goal, "muted"), "count": len(members), "share": charts.share_label(len(members), total),
            "active": statuses["Active"], "active_rate": charts.share_label(statuses["Active"], len(members)), "url": goal_url(goal),
            "split": charts.stacked_rows([(goal, statuses, "")], ENGAGEMENT_STATUSES, ENGAGEMENT_KEYS, ENGAGEMENT_LABELS)[0],
        })
    defence = [row for row in rows if row["career_goal"] == "Defence"]
    entries = Counter(row["defence_entry"] or NOT_RECORDED for row in defence)
    exams = Counter()
    for row in rows:
        if row["career_goal"] in {"UPSC / Civil Services", "Other"}:
            exams[(row["target_exam"] if row["target_exam"] != "Other" else "") or ("Other: " + row["goal_detail"][:28] if row["goal_detail"] else NOT_RECORDED)] += 1
    exam_total = sum(exams.values())
    exams = charts.fold_tail(exams, 12, other="Other exams")

    def target_link(label):
        if label in {"Other exams", NOT_RECORDED} or label.startswith("Other:"):
            return ""
        return students_url(target=label)

    stage_order = [value for value, _ in StudentProfile.PREP_STAGES] + [NOT_RECORDED]
    stage_keys = {value: f"age-{index}" for index, value in enumerate(stage_order[:-1])}
    stage_keys[NOT_RECORDED] = "age-6"
    stages_by_goal = [
        (goal, Counter(row["prep_stage"] or NOT_RECORDED for row in by_goal.get(goal, [])), goal_url(goal), GOAL_KEYS.get(goal, "muted"))
        for goal in goals if by_goal.get(goal)
    ]
    stages_present = {stage for _, counter, _, _ in stages_by_goal for stage in counter}
    years = Counter(row["target_year"] for row in rows if row["target_year"] and row["target_year"] >= today.year)
    year_points = [{"label": str(year), "tip": f"Exam in {year}", "value": years[year]} for year in sorted(years)[:5]]
    context = {
        "today_label": today_label(today), "total": total, "cards": cards,
        "engagement_legend": [{"label": ENGAGEMENT_LABELS[status], "key": ENGAGEMENT_KEYS[status]} for status in ENGAGEMENT_STATUSES],
        "entries": charts.bars(entries, total=len(defence), keys={NOT_RECORDED: "muted"}, url=target_link),
        "defence_total": len(defence),
        "exams": charts.bars(exams, total=exam_total, keys={"Other exams": "muted", NOT_RECORDED: "muted"}, url=target_link),
        "exam_total": exam_total,
        "stages": charts.stacked_rows(stages_by_goal, stage_order, stage_keys, PREP_LABELS),
        "stage_legend": [{"label": PREP_LABELS.get(stage, stage), "key": stage_keys[stage]} for stage in stage_order if stage in stages_present],
        "years": charts.columns(year_points, unit="student") if year_points else None,
        "no_year": sum(1 for row in rows if not row["target_year"]),
    }
    return render(request, "rm/career_goals.html", context)


KEPT_COMING = ("Came only once", "Less than a month", "1–3 months", "3–6 months", "6 months or more")


def _kept_coming(first, last):
    if first == last:
        return KEPT_COMING[0]
    days = (last - first).days
    return KEPT_COMING[1] if days < 30 else KEPT_COMING[2] if days < 91 else KEPT_COMING[3] if days < 182 else KEPT_COMING[4]


@rm_required("coordinator")
def analytics(request):
    today = timezone.localdate()
    all_rows = student_values(today)
    goal = request.GET.get("goal", "")
    scope = "all" if request.GET.get("who") == "all" else "active"
    goal_rows = [row for row in all_rows if row["goal"] == goal] if goal in GOAL_KEYS else all_rows
    rows = [row for row in goal_rows if row["status"] == "Active"] if scope == "active" else goal_rows
    total = len(rows)
    firsts = first_visits()

    # Enrollment each month, split by whether the student ever came.
    months, cursor = [], today.replace(day=1)
    for _ in range(12):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    came, not_yet = Counter(), Counter()
    for row in goal_rows:
        registered = row["registration_date"]
        if registered and registered >= months[0]:
            (came if row["id"] in firsts else not_yet)[(registered.year, registered.month)] += 1
    enrollment_points = [
        {"label": month.strftime("%b") if month.month != 1 else month.strftime("%b %y"), "tip": month.strftime("%B %Y"),
         "parts": {"came": came[(month.year, month.month)], "not_yet": not_yet[(month.year, month.month)]}}
        for month in months
    ]
    recent = [row for row in goal_rows if row["registration_date"] and months[0] <= row["registration_date"] <= today - timedelta(days=30)]
    within_week = sum(1 for row in recent if row["id"] in firsts and (firsts[row["id"]] - row["registration_date"]).days <= 7)
    never = sum(1 for row in recent if row["id"] not in firsts)

    stopped = [row for row in goal_rows if row["status"] == "Inactive" and row["id"] in firsts and row["last_visit"]]
    kept = Counter(_kept_coming(firsts[row["id"]], row["last_visit"]) for row in stopped)
    early = kept[KEPT_COMING[0]] + kept[KEPT_COMING[1]]

    age_labels = [label for _, label in AGE_BUCKETS]
    ages = Counter(age_label(row["dob"], today) for row in rows)
    status_filter = "Active" if scope == "active" else ""
    age_points = [
        {"label": label, "tip": f"Age {label}", "value": ages.get(label, 0), "url": students_url(age=label, engagement=status_filter, goal=goal)}
        for label in age_labels if ages.get(label, 0) or label not in {"Below 15", "Above 30"}
    ]
    requirement_counts = Counter(item for row in rows for item in (row["requirements"] or []))
    lapsed_rows = [row for row in goal_rows if row["status"] in {"Inactive", "Never Attended"}]
    lapsed_needs = Counter(item for row in lapsed_rows for item in (row["requirements"] or []))
    needs = charts.bars(requirement_counts, total=total, url=lambda item: students_url(requirement=item, engagement=status_filter, goal=goal))
    for bar in needs:
        bar["compare"] = charts.share_label(lapsed_needs.get(bar["label"], 0), len(lapsed_rows)) if scope == "active" and lapsed_rows else ""
    qualification = Counter(
        row["qualification"] if row["qualification"] in QUALIFICATIONS else (NOT_RECORDED if not row["qualification"] else "Other")
        for row in rows
    )
    missing = {
        "dob": sum(1 for row in all_rows if not row["dob"]), "goal": sum(1 for row in all_rows if not row["career_goal"]),
        "locality": sum(1 for row in all_rows if not row["locality"]),
        "phone": sum(count for count in Counter(row["phone"] for row in all_rows if row["phone"]).values() if count > 1),
    }
    expectations = [row for row in sorted(rows, key=lambda row: row["registration_date"] or today, reverse=True) if (row["expectations"] or "").strip()][:10]
    context = {
        "today_label": today_label(today), "total": total, "goal": goal, "scope": scope,
        "goal_filters": [("", "All goals")] + [(value, value) for value in GOAL_ORDER],
        "scopes": [("active", "Active students"), ("all", "Everyone enrolled")],
        "engagement": _engagement_block(goal_rows),
        "enrolled_total": len(goal_rows),
        "enrollments": charts.stacked_columns(enrollment_points, [("came", "active", "Came at least once"), ("not_yet", "never", "Haven't come yet")], unit="enrollment"),
        "conversion": {"recent": len(recent), "within_week": charts.share_label(within_week, len(recent)), "never": never, "never_share": charts.share_label(never, len(recent))},
        "kept": charts.bars(kept, total=len(stopped), order=KEPT_COMING, keys={label: f"age-{index + 1}" for index, label in enumerate(KEPT_COMING)}),
        "kept_total": len(stopped), "kept_early": charts.share_label(early, len(stopped)),
        "ages": charts.columns(age_points, unit="student"),
        "age_unknown": ages.get(NOT_RECORDED, 0),
        "gender": charts.split(
            Counter({"female": "Female", "male": "Male", "other": "Other"}.get(row["gender"], NOT_RECORDED) for row in rows),
            order=["Female", "Male", "Other", NOT_RECORDED], keys={"Female": "female", "Male": "male", "Other": "other", NOT_RECORDED: "muted"},
        ),
        "localities": charts.bars(
            charts.fold_tail(Counter(row["locality"] or NOT_RECORDED for row in rows), 10, other="Other areas"), total=total,
            keys={NOT_RECORDED: "muted", "Other areas": "muted"},
            url=lambda place: "" if place == "Other areas" else students_url(locality=NO_VALUE if place == NOT_RECORDED else place, engagement=status_filter, goal=goal),
        ),
        "purpose": charts.bars(
            Counter(row["purpose_of_rm"] or NOT_RECORDED for row in rows), total=total, keys={NOT_RECORDED: "muted"}, labels=PURPOSE_LABELS,
            url=lambda purpose: students_url(purpose=purpose, engagement=status_filter, goal=goal) if purpose != NOT_RECORDED else "",
        ),
        "needs": needs, "needs_compare": scope == "active" and bool(lapsed_rows),
        "qualification": charts.bars(
            qualification, total=total, order=QUALIFICATIONS + ("Other", NOT_RECORDED), keys={NOT_RECORDED: "muted", "Other": "muted"},
            url=lambda value: students_url(qualification=NO_VALUE if value == NOT_RECORDED else value, engagement=status_filter, goal=goal),
        ),
        "expectations": expectations, "missing": missing,
    }
    return render(request, "rm/analytics.html", context)
