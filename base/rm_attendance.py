"""Roshan Mustaqbil attendance: marking visits at the desk, visit history and
corrections."""

from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from base.rm import (
    ENROLLMENT_VISIT, GOAL_KEYS, MAX_STAY_HOURS, check_back_in, check_out, clear_check_out, desk_toggle, give_check_in_time,
    in_centre_now, initials, mark_student_present, minutes_between, normalize_phone, remove_visit_record, rm_visits,
    stay_label, stay_minutes, student_queryset,
)
from base.rm_access import rm_required
from base.rm_common import PAGE_SIZE, checkin_rows, csv_response, day_checkins, today_label
from attendance.models import Attendance
from employee.models import StudentProfile

RESULTS_SHOWN = 8
BACKDATE_DAYS = 30
# The search box's own requests: typing never marks anyone, only Enter.
SEARCH_INPUT_ID = "rm-desk-search"
ENROLLMENT_KEPT = (
    "That's the day {name} enrolled, so it stays. If the enrollment date is wrong, correct it on "
    "their details; if they were enrolled by mistake, remove the student."
)


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
    visits = {visit.employee_id_id: visit for visit in rm_visits().filter(employee_id__in=shown, attendance_date=day)}
    rows = [
        {
            "student": student, "initials": initials(student), "goal_key": GOAL_KEYS.get(student.rm_profile.career_goal, "none"),
            "is_exact": student in exact, "visit": visits.get(student.id), "state": _state(visits.get(student.id)),
        }
        for student in shown
    ]
    return exact, rows, max(total, len(candidates))


def _state(visit):
    """"out" (not here), "in" (in the centre) or "left" (checked out)."""
    if visit is None:
        return "out"
    if visit.attendance_clock_out:
        return "left"
    return "in"


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
    # In the centre first (latest arrival first), then those who have left.
    in_now = [visit for visit in visits if not visit.attendance_clock_out]
    left = sorted((visit for visit in visits if visit.attendance_clock_out), key=lambda visit: visit.attendance_clock_out, reverse=True)
    return {
        "query": query, "exact": exact, "rows": rows, "total": total, "more": max(total - len(rows), 0),
        "shared_phone": len(exact) > 1, "flash": flash, "today_label": today_label(day), "day": day, "today": today,
        "is_today": day == today, "earliest": today - timedelta(days=BACKDATE_DAYS),
        "checkins": checkin_rows(in_now + left), "today_count": len(in_now) + len(left), "regulars": regulars,
        "in_count": sum(1 for visit in in_now if visit.attendance_clock_in), "left_count": len(left),
        "untimed_count": sum(1 for visit in in_now if not visit.attendance_clock_in),
        "enrollment_visit": ENROLLMENT_VISIT,
    }


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true" and request.headers.get("HX-Sidebar-Nav") != "true"


def _desk_update(request, day, flash, query=""):
    return render(request, "rm/partials/desk_update.html", _desk_context(request, query, day, flash))


@rm_required
def quick_attendance(request):
    today = timezone.localdate()
    day = _desk_day(request, today)
    query = request.GET.get("q", "").strip()
    if request.method == "POST":
        student = get_object_or_404(student_queryset(), id=request.POST.get("student_id"))
        if request.POST.get("action") == "restore":
            record, action = _restore_visit(student, day, request.POST.get("restore_in"), request.POST.get("restore_out"), request.user)
        else:
            record, action = _desk_action(student, day, today, request.POST.get("action", "in"), request.user)
        flash = _flash(student, record, action)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"action": action, "student": student.get_full_name(), "registration": student.badge_id, "time": timezone.localtime().strftime("%I:%M %p")})
        if _is_htmx(request):
            return _desk_update(request, day, flash)
        messages.success(request, flash["text"])
        return redirect(reverse("youth-daily-attendance") + (f"?on={day.isoformat()}" if day != today else ""))
    if _is_htmx(request):
        # Enter marks the student only for a single exact registration or
        # phone match; anything less shows the list to choose from. Typing
        # (requests from the search box itself) only ever searches.
        exact, _, _ = search_students(query, day)
        pressed_enter = request.GET.get("mark_exact") and request.headers.get("HX-Trigger") != SEARCH_INPUT_ID
        if pressed_enter and len(exact) == 1:
            record, action = desk_toggle(exact[0], day=day, actor=request.user)
            return _desk_update(request, day, _flash(exact[0], record, action))
        return _desk_update(request, day, None, query)
    return render(request, "rm/quick_attendance.html", _desk_context(request, query, day))


def _restore_visit(student, day, arrived, left, actor):
    """Put back a visit removed by mistake, with the times it had."""
    def hhmm(value):
        try:
            return datetime.strptime(value or "", "%H:%M").time()
        except ValueError:
            return None

    record, created = mark_student_present(student, day=day, actor=actor)
    if not created:
        return record, "recorded"  # marked again in the meantime
    arrived, left = hhmm(arrived), hhmm(left)
    Attendance.objects.filter(pk=record.pk).update(attendance_clock_in=arrived, attendance_clock_in_date=day if arrived else None)
    record.attendance_clock_in = arrived
    if arrived and left:
        check_out(record, left)
    return record, "restored"


def _desk_action(student, day, today, action, actor):
    """A desk button: check in (or back in), or check out."""
    if day != today:
        record, created = mark_student_present(student, day=day, actor=actor)
        return record, "in" if created else "recorded"
    record = rm_visits().filter(employee_id=student, attendance_date=day).first()
    if action == "out":
        if record and record.attendance_clock_in and not record.attendance_clock_out:
            return check_out(record), "out"
        return record, "already_out" if record and record.attendance_clock_out else "not_in"
    if record is None:
        record, _ = mark_student_present(student, day=day, actor=actor)
        return record, "in"
    if not record.attendance_clock_in:
        return give_check_in_time(record), "timed"
    if record.attendance_clock_out:
        return check_back_in(record), "back"
    return record, "already_in"


def _flash(student, record, action):
    """The desk's green message after an action, with what Undo reverses."""
    name = student.get_full_name()
    at = lambda value: value.strftime("%I:%M %p").lstrip("0") if value else ""
    arrived, left = record.attendance_clock_in if record else None, record.attendance_clock_out if record else None
    texts = {
        "in": f"{name} is checked in at {at(arrived)}." if arrived else f"{name} is marked present for {record.attendance_date:%d %b}.",
        "timed": f"{name} is checked in at {at(arrived)}. They were already marked present today, without a time.",
        "restored": f"{name}'s visit is back" + (f", {at(arrived)} to {at(left)}." if arrived and left else f", in since {at(arrived)}." if arrived else "."),
        "out": f"{name} is checked out at {at(left)}, after {stay_label(stay_minutes(record))}." if stay_minutes(record) is not None else f"{name} is checked out at {at(left)}.",
        "back": f"{name} is back in the centre (first came at {at(arrived)}).",
        "just_in": f"{name} checked in at {at(arrived)}, just now. Nothing changed.",
        "just_out": f"{name} checked out at {at(left)}, just now. Nothing changed. If they've come back, use Check in again.",
        "just_back": f"{name} came back into the centre just now. Nothing changed.",
        "already_in": f"{name} is already in the centre, since {at(arrived)}. Nothing changed.",
        "already_out": f"{name} has already checked out, at {at(left)}. Nothing changed.",
        "not_in": f"{name} hasn't checked in today. Nothing changed.",
        "recorded": f"{name} is already marked present for {record.attendance_date:%d %b}. Nothing changed." if record else "",
    }
    undo = {"in": "in", "out": "out", "back": "back"}.get(action, "")
    if action == "in" and record and record.request_description == ENROLLMENT_VISIT:
        undo = ""  # enrolling is undone by removing the student, not the visit
    return {
        "action": action, "student": student, "record": record, "text": texts[action], "undo": undo,
        "changed": action in {"in", "out", "back", "timed", "restored"}, "previous_out": getattr(record, "previous_out", None),
    }


@rm_required
@require_POST
def check_out_everyone(request):
    """At closing time: check out everyone still in the centre."""
    now = timezone.localtime().replace(tzinfo=None).time()
    count = 0
    for record in in_centre_now():
        check_out(record, now)
        count += 1
    flash = {"action": "all_out", "text": f"Checked out {count} student{'s' if count != 1 else ''} at {now.strftime('%I:%M %p').lstrip('0')}.", "changed": bool(count), "undo": ""}
    if _is_htmx(request):
        return _desk_update(request, timezone.localdate(), flash)
    messages.success(request, flash["text"])
    return redirect("youth-daily-attendance")


@rm_required
@require_POST
def undo_checkin(request):
    today = timezone.localdate()
    record = get_object_or_404(rm_visits(), id=request.POST.get("record_id"), attendance_date__gte=today - timedelta(days=BACKDATE_DAYS))
    undo = request.POST.get("undo", "in")
    if undo in {"out", "back"}:
        # Undo a check-out (they're in again), or a check-back-in (they had left).
        student = record.employee_id
        if undo == "out":
            clear_check_out(record)
            flash = {"action": "undone", "text": f"{student.get_full_name()} is in the centre again.", "changed": True, "undo": ""}
        else:
            previous = request.POST.get("previous_out", "")
            try:
                check_out(record, datetime.strptime(previous, "%H:%M").time())
            except ValueError:
                check_out(record)
            flash = {"action": "undone", "text": f"{student.get_full_name()} is checked out again.", "changed": True, "undo": ""}
        if _is_htmx(request):
            return _desk_update(request, _desk_day(request, today), flash)
        messages.success(request, flash["text"])
        return redirect("youth-daily-attendance")
    if record.request_description == ENROLLMENT_VISIT:
        messages.info(request, ENROLLMENT_KEPT.format(name=record.employee_id.get_full_name()))
        return redirect("rm-student-profile", student_id=record.employee_id_id)
    student, day = record.employee_id, record.attendance_date
    times = {"restore_in": record.attendance_clock_in, "restore_out": record.attendance_clock_out}  # for "Put the visit back"
    remove_visit_record(record)
    if _is_htmx(request):
        return _desk_update(request, _desk_day(request, today), {"action": "removed", "undone": True, "student": student, "day": day, "changed": True, "undo": "", **times,
                                                                  "text": f"Removed the visit for {student.get_full_name()}" + (f" on {day:%d %b}." if day != today else ".")})
    messages.success(request, f"Removed the visit for {student.get_full_name()} on {day:%d %b %Y}.")
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = reverse("youth-daily-attendance")
    return redirect(target)


@rm_required
def remove_visit(request, record_id):
    """One visit: correct its times (a forgotten check-out, say) or remove
    it (marked by mistake). The enrollment visit can be corrected but not
    removed on its own."""
    today = timezone.localdate()
    record = get_object_or_404(rm_visits().select_related("employee_id"), id=record_id)
    back = request.GET.get("next") or request.POST.get("next") or reverse("rm-student-profile", args=[record.employee_id_id])
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = reverse("rm-student-profile", args=[record.employee_id_id])
    is_enrollment = record.request_description == ENROLLMENT_VISIT
    form = VisitTimesForm(
        request.POST if request.POST.get("action") == "times" else None,
        initial={"checked_in": record.attendance_clock_in, "checked_out": record.attendance_clock_out},
        day=record.attendance_date,
    )
    if request.method == "POST" and request.POST.get("action") == "times":
        if form.is_valid():
            arrived, left = form.cleaned_data["checked_in"], form.cleaned_data["checked_out"]
            Attendance.objects.filter(pk=record.pk).update(attendance_clock_in=arrived, attendance_clock_in_date=record.attendance_date if arrived else None)
            record.attendance_clock_in = arrived
            if left:
                check_out(record, left)
            else:
                clear_check_out(record)
            messages.success(request, f"Times saved for {record.employee_id.get_full_name()} on {record.attendance_date:%d %b %Y}.")
            return redirect(back)
    elif request.method == "POST" and not is_enrollment:
        student, day = record.employee_id, record.attendance_date
        remove_visit_record(record)
        messages.success(request, f"Removed the visit for {student.get_full_name()} on {day:%d %b %Y}.")
        return redirect(back)
    return render(request, "rm/remove_visit.html", {
        "record": record, "back": back, "is_enrollment": is_enrollment, "today": today, "form": form,
        "stay": stay_label(stay_minutes(record)),
    })


class VisitTimesForm(forms.Form):
    checked_in = forms.TimeField(required=False, label="Checked in", widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    checked_out = forms.TimeField(required=False, label="Checked out", widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))

    def __init__(self, *args, day=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.day = day

    def clean(self):
        values = super().clean()
        arrived, left = values.get("checked_in"), values.get("checked_out")
        now = timezone.localtime().replace(tzinfo=None)
        if left and not arrived:
            self.add_error("checked_in", "Enter when they checked in, too.")
        elif arrived and left and left < arrived:
            self.add_error("checked_out", "Check-out can't be before check-in.")
        elif arrived and left and (minutes_between(self.day, arrived, left) or 0) > MAX_STAY_HOURS * 60:
            self.add_error("checked_out", f"That's more than {MAX_STAY_HOURS} hours in the centre. Check the times.")
        for field in ("checked_in", "checked_out"):
            value = values.get(field)
            if value and self.day == now.date() and value > now.time():
                self.add_error(field, "That time hasn't come yet today.")
        return values


@rm_required
def attendance_history(request):
    today = timezone.localdate()
    records = rm_visits().select_related("employee_id", "employee_id__rm_profile").order_by("-attendance_date", "-attendance_clock_in")
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
    if request.GET.get("export") == "csv":
        response, writer = csv_response(f"rm-visits-{today.isoformat()}.csv", ["Date", "Checked in", "Checked out", "Minutes in the centre", "Type", "Registration number", "Student", "Phone", "Career goal"])
        for record in records.iterator():
            writer.writerow([record.attendance_date, record.attendance_clock_in or "", record.attendance_clock_out or "", stay_minutes(record) or "", visit_type(record), record.employee_id.badge_id, record.employee_id.get_full_name(), record.employee_id.phone, record.employee_id.rm_profile.career_goal])
        return response
    page = Paginator(records, PAGE_SIZE).get_page(request.GET.get("page"))
    rows, last_day = [], None
    for record in page.object_list:
        rows.append({
            "record": record, "student": record.employee_id, "initials": initials(record.employee_id),
            "goal_key": GOAL_KEYS.get(record.employee_id.rm_profile.career_goal, "none"), "new_day": record.attendance_date != last_day,
            "type": visit_type(record), "is_enrollment": record.request_description == ENROLLMENT_VISIT,
            "stay": stay_label(stay_minutes(record)),
        })
        last_day = record.attendance_date
    context = {
        "rows": rows, "page": page, "filters": filters, "query": query_string, "goals": StudentProfile.CAREER_GOALS,
        "export_url": reverse("youth-attendance-history") + "?" + urlencode({**{k: v for k, v in filters.items() if v}, "export": "csv"}),
        "ranges": (("", "Any time"), ("0", "Today"), ("7", "Last 7 days"), ("30", "Last 30 days"), ("90", "Last 90 days")),
        "today": today, "here": request.get_full_path(),
    }
    return render(request, "rm/attendance_history.html", context)


def visit_type(record):
    """Enrolled (the enrollment day), Visit, or From a register (no time)."""
    if record.request_description == ENROLLMENT_VISIT:
        return "Enrolled"
    return "Visit" if record.attendance_clock_in else "From a register"
