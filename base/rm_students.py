"""Roshan Mustaqbil student screens: the list, enrollment, the profile and
the follow-up call list."""

from datetime import date, timedelta
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from base import rm_charts as charts
from base.rm import (
    AGE_BUCKETS, ALL_STATUSES, ENGAGEMENT_HELP, ENGAGEMENT_LABELS, GOAL_KEYS, LAPSED, MOVED_ON, NO_STATUS,
    NO_VALUE, NOT_RECORDED, QUALIFICATIONS, RETRY_RESULTS, age_group, age_q, engagement_q,
    engagement_row, engagement_status, has_role, initials, mark_student_present, needs_call_q,
    normalize_phone, record_followup, rm_visits, student_queryset, target_label, valid_mobile,
    with_last_visit,
)
from base.rm_access import rm_required
from base.rm_common import (
    GENDER_LABELS, OUTCOME_LABELS, PAGE_SIZE, PREP_LABELS, PURPOSE_LABELS, STATUS_LABELS,
    csv_response, today_label,
)
from employee.models import Employee, StudentFollowUp, StudentProfile

SORTS = {
    "name": ("Name", ("employee_first_name", "employee_last_name")),
    "recent": ("Most recent visit", (F("last_visit").desc(nulls_last=True), "employee_first_name")),
    "longest": ("Longest since last visit", (F("last_visit").asc(nulls_last=True), "employee_first_name")),
    "newest": ("Newest enrollment", ("-rm_profile__registration_date", "-id")),
}
REGISTERED_RANGES = {"this_month": "Enrolled this month", "last_30": "Enrolled in the last 30 days", "last_90": "Enrolled in the last 90 days", "this_year": "Enrolled this year"}
CONTACTED = {"never": "Never contacted", "last_30": "Contacted in the last 30 days", "older": "Last contacted over 30 days ago"}
MISSING = {"dob": "No date of birth", "goal": "No career goal", "locality": "No area", "phone_dup": "Phone shared with another student"}


# ── Forms ────────────────────────────────────────────────────────────────

class PhoneField(forms.CharField):
    """A 10-digit mobile number; spaces, dashes and +91 are dropped."""

    widget = forms.TextInput(attrs={"type": "tel", "inputmode": "numeric", "autocomplete": "tel", "placeholder": "10-digit mobile number"})

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return value
        phone = normalize_phone(value)
        if not valid_mobile(phone):
            raise forms.ValidationError("Enter a 10-digit mobile number, for example 9419012345.")
        return phone


def _goal_rule(*goals):
    return ";".join(f"career_goal={goal}" for goal in goals)


class StudentRegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=200, label="Full name")
    phone = PhoneField(max_length=25, label="Phone number")
    gender = forms.ChoiceField(choices=(("", "Select gender"), *Employee.choice_gender), label="Gender")
    dob = forms.DateField(required=False, label="Date of birth", widget=forms.DateInput(attrs={"type": "date"}))
    age = forms.IntegerField(required=False, min_value=8, max_value=60, label="Age, if date of birth isn't known", widget=forms.NumberInput(attrs={"inputmode": "numeric"}))
    email = forms.EmailField(required=False, label="Email")
    registration_number = forms.CharField(max_length=50, required=False, label="Registration number", help_text="Leave blank to create one automatically.")
    locality = forms.ChoiceField(choices=(("", "Select area"), *StudentProfile.LOCALITIES), required=False, label="Area (tehsil)")
    address = forms.CharField(required=False, label="Village / address", widget=forms.Textarea(attrs={"rows": 2}))
    qualification = forms.ChoiceField(choices=(("", "Select qualification"), *((value, value) for value in QUALIFICATIONS), ("Other", "Other")), required=False, label="Highest qualification")
    qualification_other = forms.CharField(max_length=50, required=False, label="Which qualification?")
    institution = forms.CharField(required=False, label="School / college")
    career_goal = forms.ChoiceField(choices=(("", "Select career goal"), *StudentProfile.CAREER_GOALS), required=False, label="Career goal")
    defence_entry = forms.ChoiceField(choices=(("", "Select entry scheme"), *StudentProfile.DEFENCE_ENTRIES), required=False, label="Defence entry scheme")
    target_exam = forms.ChoiceField(choices=(("", "Select exam"), *StudentProfile.TARGET_EXAMS), required=False, label="Exam they're preparing for")
    goal_detail = forms.CharField(max_length=200, required=False, label="Describe the goal")
    prep_stage = forms.ChoiceField(choices=(("", "Select stage"), *StudentProfile.PREP_STAGES), required=False, label="How far along is their preparation?")
    target_year = forms.IntegerField(required=False, label="Exam year", widget=forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": "e.g. 2027"}))
    purpose_of_rm = forms.ChoiceField(choices=(("", "Select purpose"), *StudentProfile.PURPOSES), required=False, label="Main reason for joining RM")
    purpose_other = forms.CharField(required=False, label="Describe the reason")
    requirements = forms.MultipleChoiceField(required=False, label="What support do they need?", choices=[(item, item) for item in StudentProfile.REQUIREMENT_CHOICES], widget=forms.CheckboxSelectMultiple)
    requirements_other = forms.CharField(required=False, label="Other support needed")
    expectations = forms.CharField(required=False, label="What do they expect from RM?", widget=forms.Textarea(attrs={"rows": 2}))
    guardian_name = forms.CharField(required=False, label="Guardian name")
    guardian_phone = PhoneField(max_length=25, required=False, label="Guardian phone")
    registration_date = forms.DateField(required=False, initial=date.today, label="Enrollment date", widget=forms.DateInput(attrs={"type": "date"}), help_text="Change this when entering an older registration.")
    notes = forms.CharField(required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 2}))
    confirm_new = forms.BooleanField(required=False, label="This is a different student. Enroll anyway.")

    SECTIONS = (
        ("Student details", "Who they are and how to reach them.", ("full_name", "phone", "gender", "dob", "age", "locality", "address", "email", "registration_number")),
        ("Goal and preparation", "What they're working towards and where they are now.", ("career_goal", "defence_entry", "target_exam", "goal_detail", "prep_stage", "target_year", "qualification", "qualification_other", "institution")),
        ("Why they came", "Their reasons and what would help them.", ("purpose_of_rm", "purpose_other", "requirements", "requirements_other", "expectations")),
        ("Guardian and notes", "Optional, but useful for follow-up calls.", ("guardian_name", "guardian_phone", "registration_date", "notes")),
    )
    WIDE = {"address", "expectations", "requirements", "notes"}
    # field -> show when (field=value[|value]) rules, any of which may match
    CONDITIONAL = {
        "defence_entry": _goal_rule("Defence"),
        "target_exam": "career_goal=UPSC / Civil Services|Other",
        "goal_detail": "career_goal=Other;target_exam=Other",
        "purpose_other": "purpose_of_rm=Other",
        "requirements_other": "requirements=Other",
        "qualification_other": "qualification=Other",
    }
    REQUIRED_MARK = {"full_name", "phone", "gender"}

    def __init__(self, *args, duplicates=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.duplicates = duplicates or []

    def sections(self):
        for title, hint, names in self.SECTIONS:
            rows = [{"field": self[name], "wide": name in self.WIDE, "show_when": self.CONDITIONAL.get(name, ""), "required": name in self.REQUIRED_MARK} for name in names]
            yield {"title": title, "hint": hint, "rows": rows}

    def clean(self):
        values = super().clean()
        today = date.today()
        if values.get("dob") and values["dob"] >= today:
            self.add_error("dob", "The date of birth must be in the past.")
        if not values.get("dob") and not values.get("age"):
            self.add_error("dob", "Enter a date of birth, or an approximate age below.")
        if values.get("registration_date") and values["registration_date"] > today:
            self.add_error("registration_date", "The enrollment date can't be in the future.")
        year = values.get("target_year")
        if year and not today.year - 1 <= year <= today.year + 6:
            self.add_error("target_year", f"Enter a year between {today.year - 1} and {today.year + 6}.")
        if values.get("career_goal") == "Defence" and not values.get("defence_entry"):
            self.add_error("defence_entry", "Choose the Defence entry scheme.")
        if values.get("purpose_of_rm") == "Other" and not values.get("purpose_other"):
            self.add_error("purpose_other", "Describe why they are joining RM.")
        goal, exam = values.get("career_goal"), values.get("target_exam") or ""
        needs_detail = (goal == "Other" and exam in {"", "Other"}) or (goal == "UPSC / Civil Services" and exam == "Other")
        if needs_detail and not values.get("goal_detail"):
            self.add_error("goal_detail", "Say what they're preparing for.")
        if values.get("qualification") == "Other" and not values.get("qualification_other"):
            self.add_error("qualification_other", "Enter the qualification.")
        return values


class CallForm(forms.Form):
    result = forms.ChoiceField(choices=(("", "What happened?"), *StudentProfile.CURRENT_STATUSES), label="Result")
    called_on = forms.DateField(label="Date contacted", widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(required=False, label="Why did they stop coming?", widget=forms.Textarea(attrs={"rows": 2}))
    notes = forms.CharField(required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 2}))
    next_call_date = forms.DateField(required=False, label="Call again on", widget=forms.DateInput(attrs={"type": "date"}), help_text="Leave blank if no call is needed. Couldn't-reach and plans-to-come-back calls come back automatically.")

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("called_on", timezone.localdate())
        super().__init__(*args, **kwargs)

    def clean(self):
        values = super().clean()
        today = timezone.localdate()
        if values.get("called_on") and values["called_on"] > today:
            self.add_error("called_on", "The call can't be in the future.")
        if values.get("next_call_date") and values.get("called_on") and values["next_call_date"] <= values["called_on"]:
            self.add_error("next_call_date", "Pick a date after the call.")
        return values

    def save(self, profile, user):
        values = self.cleaned_data
        return record_followup(
            profile, result=values["result"], called_on=values["called_on"], reason=values["reason"],
            notes=values["notes"], next_call_date=values["next_call_date"], user=user,
        )


# ── Student list ─────────────────────────────────────────────────────────

FILTER_FIELDS = (
    "q", "engagement", "goal", "target", "purpose", "gender", "age", "locality", "requirement", "qualification",
    "prep_stage", "registered", "contacted", "current_status", "outcome", "call", "missing", "sort",
)


def _filtered_students(request, inactive_only=False, today=None):
    today = today or timezone.localdate()
    filters = {field: request.GET.get(field, "").strip() for field in FILTER_FIELDS}
    queryset = with_last_visit(student_queryset(), today)
    if inactive_only:
        queryset = queryset.filter(engagement_q("Inactive", today) | engagement_q("Never Attended", today))
    for token in filters["q"].split():
        match = Q(employee_first_name__icontains=token) | Q(employee_last_name__icontains=token) | Q(badge_id__icontains=token) | Q(rm_profile__guardian_name__icontains=token)
        digits = normalize_phone(token)
        if len(digits) >= 3:
            match |= Q(phone__contains=digits) | Q(rm_profile__guardian_phone__contains=digits)
        queryset = queryset.filter(match)
    if filters["engagement"] in ALL_STATUSES:
        queryset = queryset.filter(engagement_q(filters["engagement"], today))
    simple = {"purpose": "rm_profile__purpose_of_rm", "gender": "gender", "prep_stage": "rm_profile__prep_stage", "outcome": "rm_profile__outcome"}
    for field, lookup in simple.items():
        if filters[field]:
            queryset = queryset.filter(**{lookup: filters[field]})
    for field, lookup in (("goal", "rm_profile__career_goal"), ("locality", "rm_profile__locality")):
        if filters[field] == NO_VALUE:
            queryset = queryset.filter(**{lookup: ""})
        elif filters[field]:
            queryset = queryset.filter(**{lookup: filters[field]})
    if filters["target"]:
        queryset = queryset.filter(Q(rm_profile__defence_entry=filters["target"]) | Q(rm_profile__target_exam=filters["target"]) | Q(rm_profile__career_goal=filters["target"], rm_profile__career_goal__in=["NEET UG", "NEET PG"]))
    if filters["age"]:
        queryset = queryset.filter(age_q(filters["age"], today))
    if filters["requirement"]:
        # JSON list membership, portable across SQLite and Postgres.
        ids = [profile_id for profile_id, needs in StudentProfile.objects.values_list("employee_id", "requirements") if filters["requirement"] in (needs or [])]
        queryset = queryset.filter(id__in=ids)
    if filters["qualification"] == NO_VALUE:
        queryset = queryset.filter(Q(qualification__isnull=True) | Q(qualification=""))
    elif filters["qualification"] == "Other":
        queryset = queryset.exclude(qualification__in=QUALIFICATIONS).exclude(qualification__isnull=True).exclude(qualification="")
    elif filters["qualification"]:
        queryset = queryset.filter(qualification=filters["qualification"])
    if filters["registered"] in REGISTERED_RANGES:
        since = {"this_month": today.replace(day=1), "last_30": today - timedelta(days=29), "last_90": today - timedelta(days=89), "this_year": today.replace(month=1, day=1)}[filters["registered"]]
        queryset = queryset.filter(rm_profile__registration_date__gte=since)
    if filters["contacted"] == "never":
        queryset = queryset.filter(rm_profile__last_followup_date__isnull=True)
    elif filters["contacted"] == "last_30":
        queryset = queryset.filter(rm_profile__last_followup_date__gte=today - timedelta(days=29))
    elif filters["contacted"] == "older":
        queryset = queryset.filter(rm_profile__last_followup_date__lt=today - timedelta(days=29))
    if filters["current_status"] == NO_STATUS:
        queryset = queryset.filter(Q(rm_profile__current_status="") | Q(rm_profile__last_followup_date__lt=F("last_visit")))
    elif filters["current_status"]:
        queryset = queryset.filter(rm_profile__current_status=filters["current_status"])
    if filters["call"] == "due":
        queryset = queryset.filter(needs_call_q(today))
    if filters["missing"] == "dob":
        queryset = queryset.filter(dob__isnull=True)
    elif filters["missing"] == "goal":
        queryset = queryset.filter(rm_profile__career_goal="")
    elif filters["missing"] == "locality":
        queryset = queryset.filter(rm_profile__locality="")
    elif filters["missing"] == "phone_dup":
        phones = [phone for phone, count in _phone_counts().items() if count > 1]
        queryset = queryset.filter(phone__in=phones)
    sort = filters["sort"] if filters["sort"] in SORTS else "name"
    filters["sort"] = sort
    return queryset.order_by(*SORTS[sort][1]), filters


def _phone_counts():
    from collections import Counter

    return Counter(student_queryset().values_list("phone", flat=True))


CHIP_NAMES = {
    "q": "Search", "engagement": "Status", "goal": "Goal", "target": "Exam", "purpose": "Reason", "gender": "Gender",
    "age": "Age", "locality": "Area", "requirement": "Needs", "qualification": "Qualification", "prep_stage": "Stage",
    "registered": "Enrolled", "contacted": "Contacted", "current_status": "Doing now", "outcome": "Moved on",
    "call": "Calls", "missing": "Missing",
}


def _chip_value(field, value):
    lookup = {
        "engagement": ENGAGEMENT_LABELS, "gender": GENDER_LABELS, "purpose": PURPOSE_LABELS, "prep_stage": PREP_LABELS,
        "registered": REGISTERED_RANGES, "contacted": CONTACTED, "outcome": OUTCOME_LABELS, "missing": MISSING,
        "current_status": {NO_STATUS: "Not followed up yet", **STATUS_LABELS}, "call": {"due": "Waiting for a call"},
    }.get(field, {})
    if value == NO_VALUE:
        return NOT_RECORDED
    return lookup.get(value, value)


def _filter_chips(filters, base_url):
    chips = []
    for field, name in CHIP_NAMES.items():
        value = filters.get(field)
        if not value:
            continue
        remaining = {key: val for key, val in filters.items() if val and key != field and not (key == "sort" and val == "name")}
        chips.append({"label": f"{name}: {_chip_value(field, value)}", "url": base_url + ("?" + urlencode(remaining) if remaining else "")})
    return chips


def _export_students(queryset, today):
    response, writer = csv_response(f"rm-students-{today.isoformat()}.csv", [
        "Registration number", "Name", "Phone", "Gender", "Date of birth", "Age group", "Area", "Address", "Qualification",
        "School / college", "Career goal", "Exam", "Preparation stage", "Exam year", "Reason for joining", "Support needed",
        "Expectations", "Status", "Last visit", "Enrolled on", "Guardian name", "Guardian phone", "Doing now",
        "Last contacted", "Call again on", "Follow-up notes", "Moved on",
    ])
    for student in queryset.iterator():
        profile = student.rm_profile
        status = engagement_status(student.last_visit, today, profile.outcome)
        writer.writerow([
            student.badge_id, student.get_full_name(), student.phone, GENDER_LABELS.get(student.gender, ""), student.dob or "",
            age_group(student, today), profile.locality, student.address or "", student.qualification or "", profile.institution,
            profile.career_goal, target_label(profile), PREP_LABELS.get(profile.prep_stage, ""), profile.target_year or "",
            PURPOSE_LABELS.get(profile.purpose_of_rm, profile.purpose_of_rm), "; ".join(profile.requirements or []),
            profile.expectations, ENGAGEMENT_LABELS[status], student.last_visit or "", profile.registration_date,
            profile.guardian_name, profile.guardian_phone, STATUS_LABELS.get(profile.current_status, ""),
            profile.last_followup_date or "", profile.next_call_date or "", profile.followup_notes,
            OUTCOME_LABELS.get(profile.outcome, ""),
        ])
    return response


@rm_required("coordinator")
def students(request, inactive_only=False):
    today = timezone.localdate()
    queryset, filters = _filtered_students(request, inactive_only, today)
    if request.GET.get("export") == "csv":
        return _export_students(queryset, today)
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
    rows = []
    for student in page.object_list:
        row = engagement_row(student, student.last_visit, today)
        row["initials"] = initials(student)
        row["goal_key"] = GOAL_KEYS.get(student.rm_profile.career_goal, "none")
        row["target"] = target_label(student.rm_profile)
        row["doing_now"] = OUTCOME_LABELS.get(student.rm_profile.outcome) or STATUS_LABELS.get(student.rm_profile.current_status, "")
        rows.append(row)
    base_url = reverse("rm-inactive-students" if inactive_only else "rm-students")
    query = {key: value for key, value in filters.items() if value and not (key == "sort" and value == "name")}
    more_fields = ("target", "purpose", "gender", "age", "locality", "requirement", "qualification", "prep_stage", "registered", "contacted", "current_status", "outcome", "missing")
    context = {
        "rows": rows, "page": page, "filters": filters, "inactive_only": inactive_only, "base_url": base_url,
        "query": urlencode(query), "export_url": base_url + "?" + urlencode({**query, "export": "csv"}),
        "chips": _filter_chips(filters, base_url), "more_open": any(filters[field] for field in more_fields),
        "goals": StudentProfile.CAREER_GOALS, "purposes": StudentProfile.PURPOSES, "statuses": StudentProfile.CURRENT_STATUSES,
        "targets": StudentProfile.DEFENCE_ENTRIES + StudentProfile.TARGET_EXAMS[:-1], "genders": Employee.choice_gender,
        "engagements": [(status, ENGAGEMENT_LABELS[status]) for status in ALL_STATUSES],
        "age_groups": [label for _, label in AGE_BUCKETS] + [NOT_RECORDED], "localities": StudentProfile.LOCALITIES,
        "requirements": StudentProfile.REQUIREMENT_CHOICES[:-1], "qualifications": QUALIFICATIONS, "prep_stages": StudentProfile.PREP_STAGES,
        "registered_ranges": REGISTERED_RANGES.items(), "contacted_options": CONTACTED.items(), "outcomes": StudentProfile.OUTCOMES,
        "missing_options": MISSING.items(), "sorts": [(key, label) for key, (label, _) in SORTS.items()],
        "no_status": NO_STATUS, "no_value": NO_VALUE, "status_help": [(ENGAGEMENT_LABELS[s], ENGAGEMENT_HELP[s]) for s in ALL_STATUSES],
    }
    return render(request, "rm/students.html", context)


# ── Enrollment ───────────────────────────────────────────────────────────

def _next_registration_number():
    number = StudentProfile.objects.count() + 1
    while Employee.objects.filter(badge_id=f"RM-{number:04d}").exists():
        number += 1
    return f"RM-{number:04d}"


def _possible_duplicates(values, student=None):
    names = values["full_name"].strip().split(maxsplit=1)
    same_name = Q(employee_first_name__iexact=names[0], employee_last_name__iexact=names[1] if len(names) > 1 else "")
    matches = student_queryset().filter(Q(phone=values["phone"]) | same_name)
    if student:
        matches = matches.exclude(id=student.id)
    return list(matches[:5])


def _initial_from(student, profile):
    initial = {
        "registration_number": student.badge_id, "full_name": student.get_full_name(), "phone": student.phone,
        "email": student.email if "@rm." not in student.email else "", "dob": student.dob, "gender": student.gender,
        "address": student.address,
    }
    if student.qualification in QUALIFICATIONS:
        initial["qualification"] = student.qualification
    elif student.qualification:
        initial.update(qualification="Other", qualification_other=student.qualification)
    for field in StudentRegistrationForm.base_fields:
        if hasattr(profile, field) and field not in initial:
            initial[field] = getattr(profile, field)
    return initial


@rm_required("frontdesk")
def enroll_student(request, student_id=None):
    student = get_object_or_404(student_queryset(), id=student_id) if student_id else None
    if student and not has_role(request.user, "coordinator"):
        messages.info(request, "Ask a coordinator to change a student's details.")
        return redirect("rm-student-profile", student_id=student.id)
    from_desk = request.GET.get("next") == "desk" or request.POST.get("next") == "desk"
    if student:
        initial = _initial_from(student, student.rm_profile)
    else:
        # Coming from the desk with what was typed: a number or a name.
        prefill = request.GET.get("q", "").strip()
        looks_like_phone = prefill and not any(char.isalpha() for char in prefill) and len(normalize_phone(prefill)) >= 7
        initial = {"phone": normalize_phone(prefill)} if looks_like_phone else ({"full_name": prefill.title()} if prefill else {})
    form = StudentRegistrationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        duplicates = _possible_duplicates(values, student)
        registration = values["registration_number"].strip() or (student.badge_id if student else _next_registration_number())
        email = values["email"] or (student.email if student and "@rm." in student.email else f"{registration.lower().replace(' ', '-')}@rm.local")
        others = Employee.objects.exclude(id=student.id if student else None)
        if duplicates and not student and not values.get("confirm_new"):
            form.duplicates = duplicates
            form.add_error(None, "A student with the same phone number or name is already enrolled.")
        elif others.filter(badge_id=registration).exists():
            form.add_error("registration_number", "This registration number already belongs to another student.")
        elif others.filter(email=email).exists():
            form.add_error("email", "This email is already registered to another student.")
        else:
            is_new = student is None
            student = student or Employee()
            names = values["full_name"].strip().split(maxsplit=1)
            student.badge_id, student.employee_first_name = registration, names[0]
            student.employee_last_name = names[1] if len(names) > 1 else ""
            student.phone, student.email = values["phone"], email
            today = date.today()
            student.dob = values["dob"] or date(today.year - values["age"], 1, 1)
            student.gender, student.address = values["gender"], values["address"]
            student.qualification = values["qualification_other"] if values["qualification"] == "Other" else values["qualification"]
            student.is_active = True
            student.skip_user_creation = True  # students are records, not logins
            student.save()
            profile, _ = StudentProfile.objects.get_or_create(employee=student)
            for field in ("purpose_of_rm", "career_goal", "expectations", "requirements", "institution", "guardian_name", "guardian_phone", "notes", "locality", "prep_stage"):
                setattr(profile, field, values.get(field) or ([] if field == "requirements" else ""))
            goal = values.get("career_goal")
            profile.defence_entry = values["defence_entry"] if goal == "Defence" else ""
            profile.target_exam = values["target_exam"] if goal in {"UPSC / Civil Services", "Other"} else ""
            profile.goal_detail = values["goal_detail"] if goal == "Other" or profile.target_exam == "Other" else ""
            profile.target_year = values.get("target_year")
            profile.purpose_other = values["purpose_other"] if values.get("purpose_of_rm") == "Other" else ""
            profile.requirements_other = values["requirements_other"] if "Other" in (values.get("requirements") or []) else ""
            profile.registration_date = values.get("registration_date") or profile.registration_date or today
            profile.save()
            if from_desk and is_new:
                mark_student_present(student, actor=request.user)
                messages.success(request, f"{student.get_full_name()} is enrolled as {registration} and marked present.")
                return redirect("youth-daily-attendance")
            messages.success(request, f"{student.get_full_name()} is enrolled as {registration}." if is_new else "Student details saved.")
            return redirect("rm-student-profile", student_id=student.id)
    return render(request, "rm/enroll.html", {"form": form, "student": student, "from_desk": from_desk})


# ── Profile ──────────────────────────────────────────────────────────────

@rm_required("frontdesk")
def student_profile(request, student_id):
    student = get_object_or_404(student_queryset(), id=student_id)
    today = timezone.localdate()
    profile = student.rm_profile
    can_follow_up = has_role(request.user, "coordinator")
    call_form = CallForm(request.POST if request.POST.get("action") == "follow_up" else None)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "mark_present":
            _, created = mark_student_present(student, actor=request.user)
            messages.success(request, f"{student.get_full_name()} marked present." if created else f"{student.get_full_name()} was already marked present today.")
            return redirect("rm-student-profile", student_id=student.id)
        if action == "follow_up" and can_follow_up and call_form.is_valid():
            call_form.save(profile, request.user)
            messages.success(request, "Call saved.")
            return redirect("rm-student-profile", student_id=student.id)
        if action == "clear_outcome" and can_follow_up:
            profile.outcome, profile.outcome_date = "", None
            profile.save(update_fields=["outcome", "outcome_date"])
            messages.success(request, f"{student.get_full_name()} is back on the centre's current list.")
            return redirect("rm-student-profile", student_id=student.id)
    visits = rm_visits().filter(employee_id=student).select_related("created_by").order_by("-attendance_date", "-attendance_clock_in")
    visit_dates = list(visits.values_list("attendance_date", flat=True))
    engagement = engagement_row(student, visit_dates[0] if visit_dates else None, today)
    month_start = today.replace(day=1)
    context = {
        "student": student, "profile": profile, "engagement": engagement, "initials": initials(student),
        "goal_key": GOAL_KEYS.get(profile.career_goal, "none"), "age_group": age_group(student, today),
        "target": target_label(profile), "prep_label": PREP_LABELS.get(profile.prep_stage, ""),
        "purpose_label": PURPOSE_LABELS.get(profile.purpose_of_rm, profile.purpose_of_rm),
        "visits": visits[:12], "total_visits": len(visit_dates), "month_visits": sum(1 for day in visit_dates if day >= month_start),
        "present_today": bool(visit_dates) and visit_dates[0] == today,
        "calendar": charts.visit_calendar(visit_dates, today, weeks=53), "call_form": call_form,
        "calls": profile.followups.select_related("created_by")[:10], "status_labels": STATUS_LABELS,
        "needs_followup": engagement["status"] in LAPSED, "moved_on": engagement["status"] == MOVED_ON,
        "outcome_label": OUTCOME_LABELS.get(profile.outcome, ""), "can_follow_up": can_follow_up,
        "can_edit": can_follow_up, "gender_label": GENDER_LABELS.get(student.gender, ""),
    }
    return render(request, "rm/student_profile.html", context)


# ── Follow-up call list ──────────────────────────────────────────────────

QUEUES = (
    ("missing", "Regulars who missed this week", "Came 3 or more times in the weeks before, but not in the last 7 days. Easiest to bring back."),
    ("Dormant", "Slipping away", ENGAGEMENT_HELP["Dormant"]),
    ("Inactive", "Inactive", ENGAGEMENT_HELP["Inactive"]),
    ("Never Attended", "Never came", ENGAGEMENT_HELP["Never Attended"]),
)
CALLS_PER_PAGE = 20


def _queue_students(queue, today, goal="", locality=""):
    from base.rm_views import regulars_missing

    base = with_last_visit(student_queryset(), today)
    if goal:
        base = base.filter(rm_profile__career_goal=goal)
    if locality:
        base = base.filter(rm_profile__locality=locality)
    if queue == "missing":
        missing = dict(regulars_missing(today))
        students = list(base.filter(id__in=missing, rm_profile__outcome=""))
        return sorted(students, key=lambda student: -missing[student.id])
    queryset = base.filter(needs_call_q(today) & engagement_q(queue, today))
    order = ("-rm_profile__registration_date",) if queue == "Never Attended" else (F("last_visit").desc(nulls_last=True),)
    return queryset.order_by(*order, "employee_first_name")


def _call_stats(today, user):
    week = StudentFollowUp.objects.filter(called_on__gte=today - timedelta(days=6))
    week_total = week.count()
    reached = week.exclude(result__in=RETRY_RESULTS).count()
    recent = StudentFollowUp.objects.filter(called_on__gte=today - timedelta(days=60)).values_list("student__employee_id", "called_on")
    last_call = {}
    for student, called in recent:
        last_call[student] = max(called, last_call.get(student, called))
    came_back = {
        student for student, day in rm_visits().filter(employee_id__in=last_call, attendance_date__gte=today - timedelta(days=60)).values_list("employee_id", "attendance_date")
        if day > last_call[student]
    }
    return {
        "week": week_total, "reached": charts.share_label(reached, week_total), "came_back": len(came_back),
        "today": StudentFollowUp.objects.filter(called_on=today).count(),
        "mine_today": StudentFollowUp.objects.filter(created_at__date=today, created_by=user).count(),
    }


def _call_row(student, today):
    profile = student.rm_profile
    last = student.last_visit
    return {
        "student": student, "profile": profile, "initials": initials(student),
        "goal_key": GOAL_KEYS.get(profile.career_goal, "none"), "target": target_label(profile),
        "days_since": (today - last).days if last else None, "last_visit": last,
        "last_call": profile.followups.first(), "form": CallForm(prefix=f"s{student.id}"),
    }


@rm_required("coordinator")
def call_list(request):
    today = timezone.localdate()
    goal = request.GET.get("goal", "")
    locality = request.GET.get("locality", "")
    counts = {key: (len(_queue_students(key, today, goal, locality)) if key == "missing" else _queue_students(key, today, goal, locality).count()) for key, _, _ in QUEUES}
    queue = request.GET.get("queue") or next((key for key, _, _ in QUEUES if counts[key]), "Dormant")
    if queue not in counts:
        queue = "Dormant"

    if request.method == "POST":
        student = get_object_or_404(student_queryset(), id=request.POST.get("student_id"))
        form = CallForm(request.POST, prefix=f"s{student.id}")
        is_htmx = request.headers.get("HX-Request") == "true"
        if form.is_valid():
            entry = form.save(student.rm_profile, request.user)
            if is_htmx:
                return render(request, "rm/partials/call_saved.html", {"student": student, "entry": entry, "result_label": STATUS_LABELS.get(entry.result, entry.result), "stats": _call_stats(today, request.user)})
            messages.success(request, f"Call saved for {student.get_full_name()}.")
            return redirect(request.get_full_path())
        if is_htmx:
            student.last_visit = rm_visits().filter(employee_id=student).order_by("-attendance_date").values_list("attendance_date", flat=True).first()
            row = _call_row(student, today)
            row["form"] = form
            return render(request, "rm/partials/call_row.html", {"row": row, "queue": queue})
        messages.error(request, "Choose what happened on the call.")
        return redirect(request.get_full_path())

    page = Paginator(_queue_students(queue, today, goal, locality), CALLS_PER_PAGE).get_page(request.GET.get("page"))
    rows = [_call_row(student, today) for student in page.object_list]
    context = {
        "today_label": today_label(today), "queues": [{"key": key, "label": label, "help": help_text, "count": counts[key]} for key, label, help_text in QUEUES],
        "queue": queue, "queue_help": next(help_text for key, _, help_text in QUEUES if key == queue), "rows": rows, "page": page,
        "stats": _call_stats(today, request.user), "total_due": sum(counts.values()), "goal": goal, "locality": locality,
        "goals": StudentProfile.CAREER_GOALS, "localities": StudentProfile.LOCALITIES,
        "filter_query": urlencode({key: value for key, value in (("goal", goal), ("locality", locality)) if value}),
    }
    return render(request, "rm/call_list.html", context)


@rm_required("coordinator")
@require_POST
def delete_followup(request, followup_id):
    entry = get_object_or_404(StudentFollowUp, id=followup_id)
    profile = entry.student
    if StudentProfile.STATUS_OUTCOMES.get(entry.result) == profile.outcome:
        profile.outcome, profile.outcome_date = "", None
        profile.save(update_fields=["outcome", "outcome_date"])
    entry.delete()
    latest = profile.followups.first()
    profile.current_status = latest.result if latest else ""
    profile.last_followup_date = latest.called_on if latest else None
    profile.followup_notes = latest.notes if latest else ""
    profile.next_call_date = latest.next_call_date if latest else None
    profile.save(update_fields=["current_status", "last_followup_date", "followup_notes", "next_call_date"])
    messages.success(request, "Call removed.")
    return redirect("rm-student-profile", student_id=profile.employee_id)
