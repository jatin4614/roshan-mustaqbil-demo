from datetime import date, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from attendance.models import Attendance
from base.youth_centre import (
    ABSENT_MARKER,
    attendance_remarks,
    goal_info,
    is_absent,
)
from employee.models import Employee


def _students():
    return Employee.objects.filter(
        is_active=True, additional_info__youth_centre__isnull=False
    ).order_by("employee_first_name", "employee_last_name")


@login_required
def daily_attendance(request):
    selected_date = request.GET.get("date") or request.POST.get("date") or date.today().isoformat()
    attendance_date = date.fromisoformat(selected_date)
    students = list(_students())
    records = {item.employee_id_id: item for item in Attendance.objects.filter(employee_id__in=students, attendance_date=attendance_date)}
    if request.method == "POST":
        with transaction.atomic():
            for student in students:
                status = request.POST.get(f"status_{student.id}", "Present")
                if status not in {"Present", "Absent"}:
                    status = "Present"
                remarks = request.POST.get(f"remarks_{student.id}", "").strip()
                description = remarks if status != "Absent" else f"{ABSENT_MARKER}. {remarks}".strip()
                Attendance.objects.update_or_create(
                    employee_id=student,
                    attendance_date=attendance_date,
                    defaults={
                        "attendance_clock_in_date": attendance_date,
                        "attendance_clock_in": time(9, 0),
                        "attendance_clock_out_date": attendance_date,
                        "attendance_clock_out": time(16, 0),
                        "request_description": description,
                    },
                )
        messages.success(request, "Daily student attendance saved.")
        return redirect(f"{request.path}?date={selected_date}")
    rows = [
        {
            "student": student,
            "goal": goal_info(student),
            "record": records.get(student.id),
            "absent": is_absent(records[student.id]) if student.id in records else False,
            "remarks": attendance_remarks(records[student.id])
            if student.id in records
            else "",
        }
        for student in students
    ]
    return render(
        request,
        "attendance/youth_daily_attendance.html",
        {
            "rows": rows,
            "selected_date": selected_date,
            "total_students": len(rows),
            "present_count": len([row for row in rows if row["record"] and not row["absent"]]),
            "absent_count": len([row for row in rows if row["absent"]]),
        },
    )


@login_required
def attendance_history(request):
    records = Attendance.objects.filter(
        employee_id__additional_info__youth_centre__isnull=False
    ).select_related("employee_id").order_by("-attendance_date", "employee_id__employee_first_name")
    if request.GET.get("date"):
        records = records.filter(attendance_date=request.GET["date"])
    if request.GET.get("student"):
        records = records.filter(employee_id_id=request.GET["student"])
    if request.GET.get("goal"):
        records = [record for record in records if goal_info(record.employee_id)["goal"] == request.GET["goal"]]
    rows = [
        {
            "record": record,
            "goal": goal_info(record.employee_id)["goal"],
            "absent": is_absent(record),
            "remarks": attendance_remarks(record),
        }
        for record in records
    ]
    return render(request, "attendance/youth_attendance_history.html", {"rows": rows, "students": _students(), "goals": ("Defence", "UPSC / Civil Services", "NEET UG", "NEET PG")})
