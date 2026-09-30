"""Small shared helpers for the youth-centre MVP data kept on Employee."""

GOAL_CHOICES = ("Defence", "UPSC / Civil Services", "NEET UG", "NEET PG")
DEFENCE_SCHEMES = ("NDA", "TES", "Other Indian Army Entry Scheme")
ABSENT_MARKER = "Roshan Mustaqbil: Absent"
LEGACY_ABSENT_MARKERS = ("Youth Centre: Absent",)


def youth_info(student):
    return (student.additional_info or {}).get("youth_centre", {})


def goal_info(student):
    info = youth_info(student)
    return {
        "goal": info.get("student_goal") or info.get("student_aim_category") or "Not set",
        "defence_scheme": info.get("student_defence_entry_scheme", ""),
    }


def is_absent(attendance):
    description = attendance.request_description or ""
    return description.startswith((ABSENT_MARKER, *LEGACY_ABSENT_MARKERS))


def attendance_remarks(attendance):
    description = (attendance.request_description or "").strip()
    for marker in (ABSENT_MARKER, *LEGACY_ABSENT_MARKERS):
        if description.startswith(marker):
            return description.removeprefix(marker).lstrip(". ")
    return description
