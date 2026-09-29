"""Roshan Mustaqbil attendance: the front desk, visit history and
corrections."""

from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from base.rm import GOAL_KEYS, has_role, initials, mark_student_present, normalize_phone, rm_visits, student_queryset
from base.rm_access import rm_required
from base.rm_common import PAGE_SIZE, checkin_rows, csv_response, day_checkins, today_label
from employee.models import StudentProfile

RESULTS_SHOWN = 8
BACKDATE_DAYS = 30


def _desk_day(request, today):
    """The day being marked: today, or an earlier day from a paper register."""
    raw = (request.POST.get("on") or request.GET.get("on") or "").strip()
    try:
        day = date.fromisoformat(raw) if raw else today
    except ValueError:
        return today
    return day if today - timedelta(days=BACKDATE_DAYS) <= day <= today else today


def search_students(query, day):
    """Exact registration/phone matches first, then names that start with
    the text, then everything else that contains it."""
    if not query:
        return [], [], 0
    digits = normalize_phone(query)
    exact_q = Q(badge_id__iexact=query)
    if len(digits) >= 7:
        exact_q |= Q(phone=digits)
    exact = list(student_queryset().filter(exact_q).order_by("employee_first_name")[:10])
    queryset = student_queryset()
    for token in query.split():
        match = Q(employee_first_name__icontains=token) | Q(employee_last_name__icontains=token) | Q(badge_id__icontains=token) | Q(rm_profile__guardian_name__icontains=token)
        token_digits = normalize_phone(token)
        if len(token_digits) >= 3:
            match |= Q(phone__contains=token_digits)
        queryset = queryset.filter(match)
    total = queryset.count()
    lowered = query.lower()

    def rank(student):
        if student in exact:
            return 0
        names = (student.employee_first_name or "").lower(), (student.employee_last_name or "").lower(), (student.badge_id or "").lower()
        return 1 if any(name.startswith(lowered) for name in names) or student.get_full_name().lower().startswith(lowered) else 2

    candidates = list(queryset.order_by("employee_first_name", "employee_last_name")[:80])
    candidates = exact + [student for student in candidates if student not in exact]
    candidates.sort(key=lambda student: (rank(student), student.get_full_name()))
    shown = candidates[:RESULTS_SHOWN]
    present = dict(rm_visits().filter(employee_id__in=shown, attendance_date=day).values_list("employee_id", "attendance_clock_in"))
    rows = [
        {
            "student": student, "initials": initials(student), "goal_key": GOAL_KEYS.get(student.rm_profile.career_goal, "none"),
            "is_exact": student in exact, "is_present": student.id in present, "present_at": present.get(student.id),
        }
        for student in shown
    ]
    return exact, rows, max(total, len(candidates))


def _desk_context(request, query, day, flash=None):
    from base.rm_views import regulars_missing

    today = timezone.localdate()
    exact, rows, total = search_students(query, day)
    visits = day_checkins(day)
    regulars = []
    if not query and day == today:
        missing = [student for student, _ in regulars_missing(today)]
        present = set(rm_visits().filter(attendance_date=today).values_list("employee_id", flat=True))
        recent = rm_visits().filter(attendance_date__range=(today - timedelta(days=14), today - timedelta(days=1)))
        counts = {}
        for student in recent.values_list("employee_id", flat=True):
            counts[student] = counts.get(student, 0) + 1
        frequent = [student for student, visits in sorted(counts.items(), key=lambda item: -item[1]) if visits >= 3 and student not in present][:8]
        students = student_queryset().in_bulk(frequent)
        regulars = [
            {"student": students[student], "initials": initials(students[student]), "visits": counts[student],
             "goal_key": GOAL_KEYS.get(students[student].rm_profile.career_goal, "none"), "missed_week": student in missing}
            for student in frequent if student in students
        ]
    return {
        "query": query, "exact": exact, "rows": rows, "total": total, "more": max(total - len(rows), 0),
        "shared_phone": len(exact) > 1, "flash": flash, "today_label": today_label(day), "day": day, "today": today,
        "is_today": day == today, "earliest": today - timedelta(days=BACKDATE_DAYS),
        "checkins": checkin_rows(visits[:15]), "today_count": visits.count(), "regulars": regulars,
        "can_correct": has_role(request.user, "coordinator"),
    }


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true" and request.headers.get("HX-Sidebar-Nav") != "true"


def _desk_update(request, day, flash, query=""):
    return render(request, "rm/partials/desk_update.html", _desk_context(request, query, day, flash))


@rm_required("frontdesk")
def quick_attendance(request):
    today = timezone.localdate()
    day = _desk_day(request, today)
    query = request.GET.get("q", "").strip()
    if request.method == "POST":
        student = get_object_or_404(student_queryset(), id=request.POST.get("student_id"))
        record, created = mark_student_present(student, day=day, actor=request.user)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"created": created, "student": student.get_full_name(), "registration": student.badge_id, "time": timezone.localtime().strftime("%I:%M %p")})
        if _is_htmx(request):
            return _desk_update(request, day, {"created": created, "student": student, "record": record})
        messages.success(request, f"Attendance {'marked' if created else 'already marked'} for {student.get_full_name()}.")
        return redirect(reverse("youth-daily-attendance") + (f"?on={day.isoformat()}" if day != today else ""))
    if _is_htmx(request):
        # Enter marks the student only for a single exact registration or
        # phone match; anything less shows the list to choose from.
        exact, _, _ = search_students(query, day)
        if request.GET.get("mark_exact") and len(exact) == 1:
            record, created = mark_student_present(exact[0], day=day, actor=request.user)
            return _desk_update(request, day, {"created": created, "student": exact[0], "record": record})
        return _desk_update(request, day, None, query)
    return render(request, "rm/quick_attendance.html", _desk_context(request, query, day))


def _can_remove(user, record, today):
    """Coordinators correct any visit; the front desk only today's, or an
    earlier day they entered themselves today (a paper register)."""
    if has_role(user, "coordinator"):
        return True
    entered_today_by_them = record.created_by_id == user.id and record.created_at and timezone.localtime(record.created_at).date() == today
    return record.attendance_date == today or bool(entered_today_by_them)


@rm_required("frontdesk")
@require_POST
def undo_checkin(request):
    today = timezone.localdate()
    record = get_object_or_404(rm_visits(), id=request.POST.get("record_id"), attendance_date__gte=today - timedelta(days=BACKDATE_DAYS))
    if not _can_remove(request.user, record, today):
        messages.info(request, "Ask a coordinator to remove an older visit.")
        return redirect("youth-daily-attendance")
    student, day = record.employee_id, record.attendance_date
    record.delete()
    if _is_htmx(request):
        return _desk_update(request, _desk_day(request, today), {"undone": True, "student": student, "day": day})
    messages.success(request, f"Removed the visit for {student.get_full_name()} on {day:%d %b %Y}.")
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = reverse("youth-daily-attendance")
    return redirect(target)


@rm_required("frontdesk")
def remove_visit(request, record_id):
    """Confirm, then remove one visit (corrections from history/profile)."""
    today = timezone.localdate()
    record = get_object_or_404(rm_visits().select_related("employee_id", "created_by"), id=record_id)
    if not _can_remove(request.user, record, today):
        messages.info(request, "Ask a coordinator to remove an older visit.")
        return redirect("rm-student-profile", student_id=record.employee_id_id)
    back = request.GET.get("next") or request.POST.get("next") or reverse("rm-student-profile", args=[record.employee_id_id])
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = reverse("rm-student-profile", args=[record.employee_id_id])
    if request.method == "POST":
        student, day = record.employee_id, record.attendance_date
        record.delete()
        messages.success(request, f"Removed the visit for {student.get_full_name()} on {day:%d %b %Y}.")
        return redirect(back)
    return render(request, "rm/remove_visit.html", {"record": record, "back": back})


@rm_required("frontdesk")
def attendance_history(request):
    today = timezone.localdate()
    records = rm_visits().select_related("employee_id", "employee_id__rm_profile", "created_by").order_by("-attendance_date", "-attendance_clock_in")
    query = request.GET.get("q", "").strip()
    for token in query.split():
        match = Q(employee_id__badge_id__icontains=token) | Q(employee_id__employee_first_name__icontains=token) | Q(employee_id__employee_last_name__icontains=token)
        digits = normalize_phone(token)
        if len(digits) >= 3:
            match |= Q(employee_id__phone__contains=digits)
        records = records.filter(match)
    goal = request.GET.get("goal", "")
    if goal:
        records = records.filter(employee_id__rm_profile__career_goal=goal)
    day = request.GET.get("date", "")
    if day:
        try:
            records = records.filter(attendance_date=date.fromisoformat(day))
        except ValueError:
            messages.info(request, "That date wasn't recognised, so it was ignored.")
            day = ""
    span = request.GET.get("range", "")
    if span in {"0", "7", "30", "90"}:
        records = records.filter(attendance_date__gte=today - timedelta(days=max(int(span) - 1, 0)))
    else:
        span = ""
    filters = {"q": query, "goal": goal, "date": day, "range": span}
    query_string = urlencode({key: value for key, value in filters.items() if value})
    can_export = has_role(request.user, "coordinator")
    if request.GET.get("export") == "csv" and can_export:
        response, writer = csv_response(f"rm-visits-{today.isoformat()}.csv", ["Date", "Time", "Registration number", "Student", "Phone", "Career goal", "Marked by"])
        for record in records.iterator():
            writer.writerow([record.attendance_date, record.attendance_clock_in or "", record.employee_id.badge_id, record.employee_id.get_full_name(), record.employee_id.phone, record.employee_id.rm_profile.career_goal, _marked_by(record)])
        return response
    page = Paginator(records, PAGE_SIZE).get_page(request.GET.get("page"))
    rows, last_day = [], None
    for record in page.object_list:
        rows.append({
            "record": record, "student": record.employee_id, "initials": initials(record.employee_id),
            "goal_key": GOAL_KEYS.get(record.employee_id.rm_profile.career_goal, "none"), "new_day": record.attendance_date != last_day,
            "marked_by": _marked_by(record), "can_remove": _can_remove(request.user, record, today),
        })
        last_day = record.attendance_date
    context = {
        "rows": rows, "page": page, "filters": filters, "query": query_string, "goals": StudentProfile.CAREER_GOALS,
        "export_url": reverse("youth-attendance-history") + "?" + urlencode({**{k: v for k, v in filters.items() if v}, "export": "csv"}),
        "ranges": (("", "Any time"), ("0", "Today"), ("7", "Last 7 days"), ("30", "Last 30 days"), ("90", "Last 90 days")),
        "today": today, "can_export": can_export, "here": request.get_full_path(),
    }
    return render(request, "rm/attendance_history.html", context)


def _marked_by(record):
    user = record.created_by
    if not user:
        return ""
    employee = getattr(user, "employee_get", None)
    return employee.get_full_name() if employee else user.get_username()
