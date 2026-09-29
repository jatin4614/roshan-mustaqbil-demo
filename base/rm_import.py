"""Bring existing registers into the app from a spreadsheet (CSV).

Two imports: students (the registration register) and past attendance
(date-wise visits). Each upload is checked and previewed first; nothing is
saved until the preview is confirmed.
"""

import csv
import io
import re
from datetime import date, datetime, time

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from attendance.models import Attendance
from base.rm import normalize_phone, normalize_qualification, student_queryset, valid_mobile
from base.rm_access import rm_required
from base.rm_common import csv_response
from employee.models import Employee, StudentProfile

SESSION_KEY = "rm_import"
MAX_ROWS = 5000
STUDENT_COLUMNS = (
    "registration_number", "full_name", "phone", "gender", "date_of_birth", "age", "area", "address",
    "qualification", "school_or_college", "career_goal", "exam", "preparation_stage", "exam_year",
    "reason_for_joining", "support_needed", "expectations", "guardian_name", "guardian_phone",
    "enrollment_date", "notes",
)
VISIT_COLUMNS = ("registration_number", "phone", "date", "time")
ALIASES = {
    "name": "full_name", "student_name": "full_name", "student": "full_name", "mobile": "phone", "phone_number": "phone",
    "contact": "phone", "dob": "date_of_birth", "birth_date": "date_of_birth", "tehsil": "area", "locality": "area",
    "village": "address", "education": "qualification", "school": "school_or_college", "college": "school_or_college",
    "institution": "school_or_college", "goal": "career_goal", "target_exam": "exam", "defence_entry": "exam",
    "stage": "preparation_stage", "prep_stage": "preparation_stage", "target_year": "exam_year", "purpose": "reason_for_joining",
    "purpose_of_rm": "reason_for_joining", "requirements": "support_needed", "needs": "support_needed",
    "registration_date": "enrollment_date", "enrolled_on": "enrollment_date", "reg_no": "registration_number",
    "registration_no": "registration_number", "reg_number": "registration_number", "visit_date": "date", "check_in": "time",
}
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d/%m/%y")
GOAL_ALIASES = {
    "defence": "Defence", "defense": "Defence", "army": "Defence", "nda": "Defence", "upsc": "UPSC / Civil Services",
    "civil services": "UPSC / Civil Services", "ias": "UPSC / Civil Services", "neet": "NEET UG", "neet ug": "NEET UG",
    "neet pg": "NEET PG", "mbbs": "NEET UG",
}


def _key(header):
    key = re.sub(r"[^a-z0-9]+", "_", (header or "").strip().lower()).strip("_")
    return ALIASES.get(key, key)


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"“{value}” isn't a date (use 2024-05-31 or 31-05-2024)")


def _parse_time(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(value.upper(), fmt).time()
        except ValueError:
            continue
    raise ValueError(f"“{value}” isn't a time (use 10:30 or 2:15 PM)")


def _match(value, choices):
    """Match free text to a choice value or label, ignoring case."""
    text = (value or "").strip().lower()
    for stored, label in choices:
        if text in {stored.lower(), str(label).lower()}:
            return stored
    return ""


def _read_csv(upload):
    raw = upload.read()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    reader = csv.DictReader(io.StringIO(text))
    rows = [{_key(header): (value or "").strip() for header, value in row.items() if header} for row in reader]
    return rows[:MAX_ROWS], len(rows) > MAX_ROWS


def _check_students(rows):
    existing_phones = {}
    for student_id, phone, first, last in student_queryset().values_list("id", "phone", "employee_first_name", "employee_last_name"):
        existing_phones.setdefault(phone, []).append(f"{first} {last}".strip().lower())
    existing_badges = set(Employee.objects.exclude(badge_id__isnull=True).values_list("badge_id", flat=True))
    seen = set()
    checked = []
    for number, row in enumerate(rows, start=2):
        errors, notes = [], []
        name = " ".join(row.get("full_name", "").split())
        phone = normalize_phone(row.get("phone"))
        if not name:
            errors.append("name is missing")
        if not valid_mobile(phone):
            errors.append("phone isn't a 10-digit mobile number")
        values = {"full_name": name.title() if name.isupper() or name.islower() else name, "phone": phone, "registration_number": row.get("registration_number", "")}
        try:
            values["dob"] = _parse_date(row.get("date_of_birth"))
        except ValueError as error:
            errors.append(str(error))
        try:
            values["registration_date"] = _parse_date(row.get("enrollment_date")) or timezone.localdate()
        except ValueError as error:
            errors.append(str(error))
        if not values.get("dob") and row.get("age", "").isdigit():
            values["dob"] = date(timezone.localdate().year - int(row["age"]), 1, 1)
            notes.append("birth date estimated from age")
        gender = row.get("gender", "").lower()[:1]
        values["gender"] = {"m": "male", "f": "female", "o": "other"}.get(gender, "")
        goal_text = row.get("career_goal", "")
        goal = _match(goal_text, StudentProfile.CAREER_GOALS) or GOAL_ALIASES.get(goal_text.strip().lower(), "")
        exam_text = row.get("exam", "")
        values["career_goal"] = goal or ("Other" if goal_text else "")
        values["goal_detail"] = goal_text if goal_text and not goal else ""
        values["defence_entry"] = _match(exam_text, StudentProfile.DEFENCE_ENTRIES) if values["career_goal"] == "Defence" else ""
        if values["career_goal"] == "Defence" and not values["defence_entry"] and goal_text.strip().lower() == "nda":
            values["defence_entry"] = "NDA"
        values["target_exam"] = _match(exam_text, StudentProfile.TARGET_EXAMS) if values["career_goal"] in {"UPSC / Civil Services", "Other"} else ""
        if exam_text and not (values["defence_entry"] or values["target_exam"]) and values["career_goal"] not in {"NEET UG", "NEET PG"}:
            values["goal_detail"] = (values["goal_detail"] + " " + exam_text).strip()
        values["prep_stage"] = _match(row.get("preparation_stage"), StudentProfile.PREP_STAGES)
        year = row.get("exam_year", "")
        values["target_year"] = int(year) if year.isdigit() and 2000 < int(year) < 2100 else None
        area = row.get("area", "")
        values["locality"] = _match(area, StudentProfile.LOCALITIES) or ("Other" if area else "")
        values["address"] = ", ".join(part for part in (row.get("address", ""), area if values["locality"] == "Other" else "") if part)
        values["qualification"] = normalize_qualification(row.get("qualification"))
        values["institution"] = row.get("school_or_college", "")
        reason = row.get("reason_for_joining", "")
        values["purpose_of_rm"] = _match(reason, StudentProfile.PURPOSES) or ("Other" if reason else "")
        values["purpose_other"] = reason if reason and values["purpose_of_rm"] == "Other" else ""
        needs, unknown = [], []
        for item in re.split(r"[;,]", row.get("support_needed", "")):
            item = item.strip()
            if not item:
                continue
            matched = next((choice for choice in StudentProfile.REQUIREMENT_CHOICES if choice.lower() == item.lower()), "")
            (needs if matched else unknown).append(matched or item)
        if unknown:
            needs.append("Other")
        values["requirements"] = list(dict.fromkeys(needs))
        values["requirements_other"] = ", ".join(unknown)
        values["expectations"] = row.get("expectations", "")
        values["guardian_name"] = row.get("guardian_name", "")
        values["guardian_phone"] = normalize_phone(row.get("guardian_phone"))
        values["notes"] = row.get("notes", "")
        key = (phone, name.lower())
        if errors:
            state = "error"
        elif values["registration_number"] and values["registration_number"] in existing_badges:
            state, notes = "exists", notes + ["registration number already enrolled"]
        elif name.lower() in existing_phones.get(phone, []):
            state, notes = "exists", notes + ["already enrolled with this phone"]
        elif key in seen:
            state, notes = "exists", notes + ["repeated in this file"]
        else:
            state = "new"
            if phone in existing_phones:
                notes.append("phone also used by another student")
        seen.add(key)
        values["dob"] = values["dob"].isoformat() if values.get("dob") else ""
        values["registration_date"] = values["registration_date"].isoformat() if values.get("registration_date") else ""
        checked.append({"line": number, "state": state, "errors": errors, "notes": notes, "values": values})
    return checked


def _check_visits(rows):
    by_badge = {badge.lower(): student_id for student_id, badge in student_queryset().exclude(badge_id__isnull=True).values_list("id", "badge_id")}
    by_phone = {}
    for student_id, phone in student_queryset().values_list("id", "phone"):
        by_phone.setdefault(phone, []).append(student_id)
    names = dict((student_id, f"{first} {last}".strip()) for student_id, first, last in student_queryset().values_list("id", "employee_first_name", "employee_last_name"))
    existing = set(Attendance.objects.filter(employee_id__in=names).values_list("employee_id", "attendance_date"))
    today = timezone.localdate()
    checked, seen = [], set()
    for number, row in enumerate(rows, start=2):
        errors, notes = [], []
        student_id = by_badge.get(row.get("registration_number", "").lower())
        if not student_id:
            matches = by_phone.get(normalize_phone(row.get("phone")), [])
            if len(matches) == 1:
                student_id = matches[0]
            elif len(matches) > 1:
                errors.append("phone is shared by several students; give the registration number")
            else:
                errors.append("no enrolled student with this registration number or phone")
        try:
            day = _parse_date(row.get("date"))
            if not day:
                errors.append("date is missing")
            elif day > today:
                errors.append("date is in the future")
        except ValueError as error:
            errors.append(str(error))
            day = None
        try:
            arrived = _parse_time(row.get("time"))
        except ValueError as error:
            errors.append(str(error))
            arrived = None
        state = "error" if errors else "exists" if (student_id, day) in existing or (student_id, day) in seen else "new"
        if state == "exists":
            notes.append("visit already recorded")
        seen.add((student_id, day))
        checked.append({
            "line": number, "state": state, "errors": errors, "notes": notes,
            "values": {"student_id": student_id, "name": names.get(student_id, ""), "date": day.isoformat() if day else "", "time": arrived.strftime("%H:%M") if arrived else ""},
        })
    return checked


def _import_students(checked):
    rows = [row["values"] for row in checked if row["state"] == "new"]
    badges = set(Employee.objects.exclude(badge_id__isnull=True).values_list("badge_id", flat=True))
    emails = set(Employee.objects.values_list("email", flat=True))
    number = StudentProfile.objects.count() + 1
    employees = []
    for values in rows:
        badge = values["registration_number"]
        if not badge:
            while f"RM-{number:04d}" in badges:
                number += 1
            badge = f"RM-{number:04d}"
        badges.add(badge)
        email, suffix = f"{badge.lower().replace(' ', '-')}@rm.local", 1
        while email in emails:
            suffix += 1
            email = f"{badge.lower().replace(' ', '-')}-{suffix}@rm.local"
        emails.add(email)
        names = values["full_name"].split(maxsplit=1)
        employees.append(Employee(
            badge_id=badge, employee_first_name=names[0], employee_last_name=names[1] if len(names) > 1 else "",
            email=email, phone=values["phone"], gender=values["gender"] or None,
            dob=date.fromisoformat(values["dob"]) if values["dob"] else None, address=values["address"],
            qualification=values["qualification"], is_active=True,
        ))
    # bulk_create: students are records, so none of the HR employee set-up
    # (logins, work information) is wanted.
    Employee.objects.bulk_create(employees, batch_size=200)
    created = {employee.email: employee for employee in Employee.objects.filter(email__in=[employee.email for employee in employees])}
    profiles = []
    for employee, values in zip(employees, rows):
        profiles.append(StudentProfile(
            employee=created[employee.email], career_goal=values["career_goal"], defence_entry=values["defence_entry"],
            target_exam=values["target_exam"], goal_detail=values["goal_detail"], prep_stage=values["prep_stage"],
            target_year=values["target_year"], locality=values["locality"], purpose_of_rm=values["purpose_of_rm"],
            purpose_other=values["purpose_other"], requirements=values["requirements"], requirements_other=values["requirements_other"],
            expectations=values["expectations"], institution=values["institution"], guardian_name=values["guardian_name"],
            guardian_phone=values["guardian_phone"], notes=values["notes"],
            registration_date=date.fromisoformat(values["registration_date"]) if values["registration_date"] else timezone.localdate(),
        ))
    StudentProfile.objects.bulk_create(profiles, batch_size=200)
    return len(profiles)


def _import_visits(checked, user):
    visits = []
    for row in checked:
        if row["state"] != "new":
            continue
        values = row["values"]
        day = date.fromisoformat(values["date"])
        arrived = time.fromisoformat(values["time"]) if values["time"] else None
        visits.append(Attendance(
            employee_id_id=values["student_id"], attendance_date=day, attendance_clock_in_date=day, attendance_clock_in=arrived,
            attendance_worked_hour="00:00", minimum_hour="00:00", request_description="Roshan Mustaqbil visit (imported)",
            created_by=user,
        ))
    before = Attendance.objects.count()
    Attendance.objects.bulk_create(visits, batch_size=500, ignore_conflicts=True)
    return Attendance.objects.count() - before


@rm_required("coordinator")
def import_data(request):
    kind = request.POST.get("kind") or request.GET.get("kind") or "students"
    kind = kind if kind in {"students", "visits"} else "students"
    if request.GET.get("template"):
        columns = STUDENT_COLUMNS if kind == "students" else VISIT_COLUMNS
        response, writer = csv_response(f"rm-{kind}-template.csv", columns)
        if kind == "students":
            writer.writerow(["", "Asma Lone", "9419012345", "Female", "2006-04-15", "", "Handwara", "Qalamabad", "Class 12", "Govt. Degree College Handwara", "NEET UG", "", "Building basics", "2026", "Competitive exam preparation", "Study Space; Mock Tests", "Quiet place to study", "Nazir Lone", "9596012345", "2024-06-01", ""])
        else:
            writer.writerow(["RM-0001", "", "2024-06-03", "10:15"])
        return response
    step = request.POST.get("step")
    if request.method == "POST" and step == "check":
        upload = request.FILES.get("file")
        if not upload or not upload.name.lower().endswith(".csv"):
            messages.error(request, "Choose a CSV file. In Excel use File, Save As, “CSV UTF-8”.")
            return redirect(f"{request.path}?kind={kind}")
        rows, truncated = _read_csv(upload)
        if not rows:
            messages.error(request, "That file has no rows under the heading row.")
            return redirect(f"{request.path}?kind={kind}")
        checked = _check_students(rows) if kind == "students" else _check_visits(rows)
        request.session[SESSION_KEY] = {"kind": kind, "rows": checked, "file": upload.name}
        return redirect(f"{request.path}?kind={kind}&preview=1")
    if request.method == "POST" and step == "confirm":
        payload = request.session.pop(SESSION_KEY, None)
        if not payload:
            messages.error(request, "The preview expired. Upload the file again.")
            return redirect(f"{request.path}?kind={kind}")
        with transaction.atomic():
            if payload["kind"] == "students":
                count = _import_students(payload["rows"])
                messages.success(request, f"Imported {count} student{'' if count == 1 else 's'}.")
                return redirect("rm-students")
            count = _import_visits(payload["rows"], request.user)
            messages.success(request, f"Imported {count} visit{'' if count == 1 else 's'}.")
            return redirect("youth-attendance-history")
    if request.method == "POST" and step == "cancel":
        request.session.pop(SESSION_KEY, None)
        return redirect(f"{request.path}?kind={kind}")
    preview = None
    payload = request.session.get(SESSION_KEY)
    if request.GET.get("preview") and payload and payload["kind"] == kind:
        rows = payload["rows"]
        preview = {
            "file": payload["file"], "rows": rows[:200], "hidden": max(len(rows) - 200, 0), "total": len(rows),
            "new": sum(1 for row in rows if row["state"] == "new"), "exists": sum(1 for row in rows if row["state"] == "exists"),
            "errors": sum(1 for row in rows if row["state"] == "error"),
        }
    context = {
        "kind": kind, "preview": preview, "student_columns": STUDENT_COLUMNS, "visit_columns": VISIT_COLUMNS,
        "goals": [value for value, _ in StudentProfile.CAREER_GOALS], "areas": [value for value, _ in StudentProfile.LOCALITIES],
    }
    return render(request, "rm/import.html", context)
