"""RM-only screens.  They deliberately avoid the generic HR employee UX."""

from collections import Counter, defaultdict
from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from attendance.models import Attendance
from base.rm import (
    AGE_BUCKETS, ENGAGEMENT_STATUSES, age_group, engagement_for_students,
    goal_label, mark_student_present, requirement_counts, student_queryset,
)
from employee.models import Employee, StudentProfile


class StudentRegistrationForm(forms.Form):
    registration_number = forms.CharField(max_length=50, required=False)
    full_name = forms.CharField(max_length=200)
    phone = forms.CharField(max_length=25)
    email = forms.EmailField(required=False)
    dob = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    gender = forms.ChoiceField(choices=(("", "Select gender"), *Employee.choice_gender), required=False)
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    qualification = forms.CharField(required=False)
    institution = forms.CharField(required=False)
    registration_date = forms.DateField(required=False, initial=date.today, widget=forms.DateInput(attrs={"type": "date"}))
    purpose_of_rm = forms.ChoiceField(choices=(("", "Select purpose"), *StudentProfile.PURPOSES), required=False)
    purpose_other = forms.CharField(required=False)
    career_goal = forms.ChoiceField(choices=(("", "Select career goal"), *StudentProfile.CAREER_GOALS), required=False)
    defence_entry = forms.ChoiceField(choices=(("", "Not applicable"), *StudentProfile.DEFENCE_ENTRIES), required=False)
    expectations = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    requirements = forms.MultipleChoiceField(required=False, choices=[(item, item) for item in StudentProfile.REQUIREMENT_CHOICES], widget=forms.CheckboxSelectMultiple)
    requirements_other = forms.CharField(required=False)
    guardian_name = forms.CharField(required=False)
    guardian_phone = forms.CharField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def clean(self):
        values = super().clean()
        if values.get("career_goal") == "Defence" and not values.get("defence_entry"):
            self.add_error("defence_entry", "Choose the Defence entry scheme.")
        return values


class FollowUpForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = ("current_status", "inactivity_reason", "last_followup_date", "followup_notes")
        widgets = {"last_followup_date": forms.DateInput(attrs={"type": "date"}), "inactivity_reason": forms.Textarea(attrs={"rows": 2}), "followup_notes": forms.Textarea(attrs={"rows": 3})}


def _admin_required(request):
    return request.user.is_superuser or request.user.has_perm("employee.view_employee")


def _student_rows(request):
    students = list(student_queryset().order_by("employee_first_name", "employee_last_name"))
    query = request.GET.get("q", "").strip()
    if query:
        students = [student for student in students if query.lower() in (student.badge_id or "").lower() or query.lower() in (student.phone or "").lower() or query.lower() in student.get_full_name().lower()]
    rows = engagement_for_students(students)
    filters = {
        "engagement": request.GET.get("engagement", ""), "goal": request.GET.get("goal", ""),
        "gender": request.GET.get("gender", ""), "purpose": request.GET.get("purpose", ""),
        "age": request.GET.get("age", ""), "defence_entry": request.GET.get("defence_entry", ""),
        "current_status": request.GET.get("current_status", ""),
    }
    filtered = []
    for row in rows:
        student, profile = row["student"], row["student"].rm_profile
        if filters["engagement"] and row["status"] != filters["engagement"]: continue
        if filters["goal"] and profile.career_goal != filters["goal"]: continue
        if filters["gender"] and student.gender != filters["gender"]: continue
        if filters["purpose"] and profile.purpose_of_rm != filters["purpose"]: continue
        if filters["age"] and age_group(student) != filters["age"]: continue
        if filters["defence_entry"] and profile.defence_entry != filters["defence_entry"]: continue
        if filters["current_status"] and profile.current_status != filters["current_status"]: continue
        row["age_group"] = age_group(student)
        filtered.append(row)
    return filtered, filters


@login_required
def students(request, inactive_only=False):
    if not _admin_required(request): return redirect("dashboard")
    rows, filters = _student_rows(request)
    if inactive_only:
        rows = [row for row in rows if row["status"] in {"Inactive", "Never Attended"}]
    return render(request, "rm/students.html", {"rows": rows, "filters": filters, "inactive_only": inactive_only, "goals": StudentProfile.CAREER_GOALS, "purposes": StudentProfile.PURPOSES, "statuses": StudentProfile.CURRENT_STATUSES, "age_groups": [label for _, label in AGE_BUCKETS]})


@login_required
def enroll_student(request, student_id=None):
    student = get_object_or_404(student_queryset(), id=student_id) if student_id else None
    profile = student.rm_profile if student else None
    initial = {}
    if student:
        initial = {"registration_number": student.badge_id, "full_name": student.get_full_name(), "phone": student.phone, "email": student.email if "@rm.local" not in student.email else "", "dob": student.dob, "gender": student.gender, "address": student.address, "qualification": student.qualification}
        for field in StudentRegistrationForm.base_fields:
            if profile and hasattr(profile, field): initial[field] = getattr(profile, field)
    form = StudentRegistrationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        names = values["full_name"].strip().split(maxsplit=1)
        registration = values["registration_number"].strip() or f"RM-{StudentProfile.objects.count()+1:04d}"
        email = values["email"] or f"{registration.lower().replace(' ', '-') }@rm.local"
        if not student:
            if Employee.objects.filter(badge_id=registration).exists(): form.add_error("registration_number", "This registration number already exists.")
            elif Employee.objects.filter(email=email).exists(): form.add_error("email", "This email is already registered.")
            else: student = Employee()
        if student and not form.errors:
            student.badge_id, student.employee_first_name = registration, names[0]
            student.employee_last_name = names[1] if len(names) > 1 else ""
            student.phone, student.email, student.dob = values["phone"], email, values["dob"]
            student.gender, student.address, student.qualification = values["gender"] or "male", values["address"], values["qualification"]
            student.is_active = True
            student.save()
            profile, _ = StudentProfile.objects.get_or_create(employee=student)
            for field in ("purpose_of_rm", "purpose_other", "career_goal", "expectations", "requirements", "requirements_other", "registration_date", "institution", "guardian_name", "guardian_phone", "notes"):
                setattr(profile, field, values.get(field) or ([] if field == "requirements" else ""))
            profile.defence_entry = values["defence_entry"] if values.get("career_goal") == "Defence" else ""
            profile.save()
            messages.success(request, "Student registration saved.")
            return redirect("rm-student-profile", student_id=student.id)
    return render(request, "rm/enroll.html", {"form": form, "student": student})


@login_required
def quick_attendance(request):
    today = timezone.localdate()
    query = request.GET.get("q", "").strip()
    result = None
    matches = []
    if query:
        exact = student_queryset().filter(Q(badge_id__iexact=query) | Q(phone__iexact=query)).first()
        if exact: result = exact
        else:
            matches = list(student_queryset().filter(Q(employee_first_name__icontains=query) | Q(employee_last_name__icontains=query) | Q(badge_id__icontains=query) | Q(phone__icontains=query)).order_by("employee_first_name")[:8])
    if request.method == "POST":
        student = get_object_or_404(student_queryset(), id=request.POST.get("student_id"))
        record, created = mark_student_present(student, actor=request.user)
        payload = {"created": created, "student": student.get_full_name(), "registration": student.badge_id, "time": timezone.localtime().strftime("%I:%M %p")}
        if request.headers.get("x-requested-with") == "XMLHttpRequest": return JsonResponse(payload)
        messages.success(request, f"Attendance {'marked' if created else 'already marked'} for {student.get_full_name()}.")
        return redirect("youth-daily-attendance")
    recent = Attendance.objects.filter(employee_id__rm_profile__isnull=False, attendance_date=today).select_related("employee_id").order_by("-attendance_clock_in")[:12]
    return render(request, "rm/quick_attendance.html", {"query": query, "result": result, "matches": matches, "recent": recent, "today_count": Attendance.objects.filter(employee_id__rm_profile__isnull=False, attendance_date=today).count()})


@login_required
def attendance_history(request):
    records = Attendance.objects.filter(employee_id__rm_profile__isnull=False).select_related("employee_id", "employee_id__rm_profile").order_by("-attendance_date", "-attendance_clock_in")
    query = request.GET.get("q", "").strip()
    if query: records = records.filter(Q(employee_id__badge_id__icontains=query) | Q(employee_id__phone__icontains=query) | Q(employee_id__employee_first_name__icontains=query) | Q(employee_id__employee_last_name__icontains=query))
    if request.GET.get("goal"): records = records.filter(employee_id__rm_profile__career_goal=request.GET["goal"])
    if request.GET.get("date"): records = records.filter(attendance_date=request.GET["date"])
    if request.GET.get("range"):
        records = records.filter(attendance_date__gte=timezone.localdate() - timedelta(days=int(request.GET["range"])))
    return render(request, "rm/attendance_history.html", {"records": records[:500], "goals": StudentProfile.CAREER_GOALS})


@login_required
def student_profile(request, student_id):
    student = get_object_or_404(student_queryset(), id=student_id)
    visits = Attendance.objects.filter(employee_id=student).order_by("-attendance_date", "-attendance_clock_in")
    engagement = engagement_for_students([student])[0]
    followup = FollowUpForm(request.POST or None, instance=student.rm_profile)
    if request.method == "POST" and followup.is_valid():
        followup.save(); messages.success(request, "Follow-up details saved."); return redirect("rm-student-profile", student_id=student.id)
    month_start = timezone.localdate().replace(day=1)
    return render(request, "rm/student_profile.html", {"student": student, "profile": student.rm_profile, "engagement": engagement, "visits": visits[:20], "total_visits": visits.count(), "month_visits": visits.filter(attendance_date__gte=month_start).count(), "followup": followup})


def _charts(students, engagement_rows):
    def groups(items):
        values = Counter(items)
        maximum = max(values.values(), default=1)
        return [
            {"label": key or "Not recorded", "count": value, "percent": round(value / maximum * 100)}
            for key, value in values.most_common()
        ]
    return {"goals": groups(student.rm_profile.career_goal for student in students), "gender": groups(student.gender for student in students), "age": groups(age_group(student) for student in students), "purpose": groups(student.rm_profile.purpose_of_rm for student in students), "requirements": groups(requirement_counts(students).elements()), "engagement": groups(row["status"] for row in engagement_rows), "inactive_status": groups(row["student"].rm_profile.current_status for row in engagement_rows if row["status"] in {"Inactive", "Never Attended"})}


@login_required
def rm_dashboard(request, attendance_only=False, analytics=False, goals=False):
    students = list(student_queryset())
    engagement_rows = engagement_for_students(students)
    today = timezone.localdate()
    visits = Attendance.objects.filter(employee_id__rm_profile__isnull=False)
    today_visits = visits.filter(attendance_date=today)
    last_30 = visits.filter(attendance_date__gte=today-timedelta(days=29))
    trend = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        trend.append({"label": day.strftime("%d %b"), "count": visits.filter(attendance_date=day).count()})
    peak = max((item["count"] for item in trend), default=1)
    for item in trend:
        item["percent"] = round(item["count"] / peak * 100) if peak else 0
    engagement_counts = Counter(row["status"] for row in engagement_rows)
    context = {"students": students, "engagement_rows": engagement_rows, "charts": _charts(students, engagement_rows), "trend": trend, "recent": today_visits.select_related("employee_id").order_by("-attendance_clock_in")[:10], "kpis": {"registered": len(students), "active": engagement_counts["Active"], "dormant": engagement_counts["Dormant"], "inactive": engagement_counts["Inactive"] + engagement_counts["Never Attended"], "never": engagement_counts["Never Attended"], "today": today_visits.count(), "week": visits.filter(attendance_date__gte=today-timedelta(days=6)).values("employee_id").distinct().count(), "month": last_30.values("employee_id").distinct().count(), "average_daily": round(last_30.count()/30, 1), "new_month": StudentProfile.objects.filter(registration_date__year=today.year, registration_date__month=today.month).count()}}
    template = "rm/analytics.html" if analytics else "rm/career_goals.html" if goals else "rm/attendance_dashboard.html" if attendance_only else "rm/dashboard.html"
    return render(request, template, context)
