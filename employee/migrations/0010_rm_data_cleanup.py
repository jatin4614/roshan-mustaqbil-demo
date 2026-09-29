"""Bring existing Roshan Mustaqbil records in line with the new fields.

* follow-up details kept on the profile become the first entry of the new
  call log, and students recorded as selected / moved away get an outcome;
* purposes that duplicated "support needed" options are folded into it;
* phone numbers are stored as plain 10-digit numbers;
* free-text qualifications are mapped onto the fixed list where obvious;
* the area (tehsil) is read from the address where it names one;
* the three staff roles are created, and any login that was created for a
  student by the HR employee model is switched off.
"""

import re

from django.db import migrations

PURPOSE_MOVES = {
    "Access to Study Material": ("Self Study", "Books / Study Material"),
    "Internet / Digital Resources": ("Self Study", "Internet"),
    "Counselling / Mentorship": ("Career Guidance", "Counselling"),
}
STATUS_OUTCOMES = {
    "Joined Armed Forces / Selected": "Selected",
    "Joined Professional Course": "Joined Professional Course",
    "Moved / Relocated": "Moved Away",
    "No Longer Interested": "Closed",
}
LOCALITIES = (
    "Kupwara", "Handwara", "Trehgam", "Kralpora", "Lolab", "Sogam", "Villgam",
    "Drugmulla", "Kalaroos", "Karnah", "Machil", "Langate", "Qalamabad", "Rajwar",
    "Zachaldara", "Magam", "Chowkibal", "Keran",
)
LOCALITY_ALIASES = {"tangdar": "Karnah"}
ROLE_GROUPS = ("RM Front desk", "RM Coordinator", "RM Manager")


def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits or (value or "")


def normalize_qualification(value):
    text = (value or "").strip().lower()
    if not text:
        return value
    if re.search(r"post|master|\bm\.?\s?(a|sc|com|tech)\b|mba|mca", text):
        return "Postgraduate"
    if re.search(r"bachelor|graduat|\bb\.?\s?(a|sc|com|tech|e)\b|mbbs|bds|degree", text):
        return "Bachelor's Degree"
    if "diploma" in text or "polytechnic" in text or "iti" in text:
        return "Diploma"
    if re.search(r"\b12|xii|higher secondary|hsc|intermediate", text):
        return "Class 12"
    if re.search(r"\b10|\bx\b|matric|ssc", text):
        return "Class 10"
    return value


def locality_from(address):
    text = (address or "").lower()
    for alias, locality in LOCALITY_ALIASES.items():
        if alias in text:
            return locality
    for locality in LOCALITIES:
        if locality.lower() in text:
            return locality
    return ""


def forwards(apps, schema_editor):
    StudentProfile = apps.get_model("employee", "StudentProfile")
    StudentFollowUp = apps.get_model("employee", "StudentFollowUp")
    Employee = apps.get_model("employee", "Employee")
    Group = apps.get_model("auth", "Group")

    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)

    followups = []
    for profile in StudentProfile.objects.select_related("employee").iterator():
        changed = set()
        if profile.purpose_of_rm in PURPOSE_MOVES:
            purpose, requirement = PURPOSE_MOVES[profile.purpose_of_rm]
            profile.purpose_of_rm = purpose
            requirements = list(profile.requirements or [])
            if requirement not in requirements:
                requirements.append(requirement)
            profile.requirements = requirements
            changed |= {"purpose_of_rm", "requirements"}
        guardian_phone = normalize_phone(profile.guardian_phone)
        if guardian_phone != profile.guardian_phone:
            profile.guardian_phone = guardian_phone
            changed.add("guardian_phone")
        if not profile.locality:
            locality = locality_from(profile.employee.address)
            if locality:
                profile.locality = locality
                changed.add("locality")
        if profile.current_status and not profile.outcome and profile.current_status in STATUS_OUTCOMES:
            profile.outcome = STATUS_OUTCOMES[profile.current_status]
            profile.outcome_date = profile.last_followup_date
            changed |= {"outcome", "outcome_date"}
        if (profile.current_status or profile.last_followup_date) and not StudentFollowUp.objects.filter(student=profile).exists():
            followups.append(StudentFollowUp(
                student=profile,
                called_on=profile.last_followup_date or profile.registration_date,
                result=profile.current_status or "Other",
                reason=profile.inactivity_reason,
                notes=profile.followup_notes,
            ))
        if changed:
            profile.save(update_fields=sorted(changed))

        employee = profile.employee
        emp_changed = []
        phone = normalize_phone(employee.phone)
        if phone != employee.phone:
            employee.phone = phone
            emp_changed.append("phone")
        qualification = normalize_qualification(employee.qualification)
        if qualification != employee.qualification:
            employee.qualification = qualification
            emp_changed.append("qualification")
        if emp_changed:
            Employee.objects.filter(pk=employee.pk).update(**{field: getattr(employee, field) for field in emp_changed})

    StudentFollowUp.objects.bulk_create(followups, batch_size=500)

    # Students are records, not users: switch off any login the HR employee
    # model created for them (staff and administrators are left alone).
    student_users = Employee.objects.filter(
        rm_profile__isnull=False, employee_user_id__isnull=False,
        employee_user_id__is_superuser=False, employee_user_id__is_staff=False,
    ).exclude(employee_user_id__groups__name__in=ROLE_GROUPS).values_list("employee_user_id", flat=True)
    HorillaUser = apps.get_model("horilla_auth", "HorillaUser")
    HorillaUser.objects.filter(id__in=list(student_users)).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0009_rm_followups_outcomes_prep"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("horilla_auth", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
