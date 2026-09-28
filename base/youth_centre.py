"""Small shared helpers for the youth-centre MVP data kept on Employee."""

GOAL_CHOICES = ("Defence", "UPSC / Civil Services", "NEET UG", "NEET PG")
DEFENCE_SCHEMES = ("NDA", "TES", "Other Indian Army Entry Scheme")
PREPARATION_STATUSES = (
    "Not Started",
    "Preparing",
    "On Track",
    "Needs Attention",
    "Exam Ready",
    "Achieved",
)
LEGACY_PREPARATION_STATUSES = {"Started": "Preparing"}
ABSENT_MARKER = "Roshan Mustaqbil: Absent"
LEGACY_ABSENT_MARKERS = ("Youth Centre: Absent",)


def youth_info(student):
    return (student.additional_info or {}).get("youth_centre", {})


def preparation_status(value):
    return LEGACY_PREPARATION_STATUSES.get(value, value or "Not Started")


def goal_info(student):
    info = youth_info(student)
    return {
        "goal": info.get("student_goal") or info.get("student_aim_category") or "Not set",
        "defence_scheme": info.get("student_defence_entry_scheme", ""),
        "preparation_status": preparation_status(info.get("student_preparation_status")),
        "progress_percentage": int(info.get("student_progress_percentage") or 0),
        "remarks": info.get("student_admin_remarks", ""),
        "last_progress_update": info.get("student_last_progress_update", ""),
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
