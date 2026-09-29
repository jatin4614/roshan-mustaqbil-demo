"""Students enroll in person at the centre, so the enrollment day is a visit.

Records entered before this rule existed may have no attendance on that day
(for example students who "never came"). Add the missing enrollment visits
so every student's history starts on the day they enrolled.
"""

import datetime

from django.db import migrations

ENROLLMENT_VISIT = "Enrolled at the centre"


def forwards(apps, schema_editor):
    StudentProfile = apps.get_model("employee", "StudentProfile")
    Attendance = apps.get_model("attendance", "Attendance")
    today = datetime.date.today()
    visited = set(
        Attendance.objects.filter(employee_id__rm_profile__isnull=False).values_list("employee_id", "attendance_date")
    )
    missing = [
        Attendance(
            employee_id_id=employee_id, attendance_date=registered, attendance_clock_in_date=registered,
            attendance_worked_hour="00:00", minimum_hour="00:00", request_description=ENROLLMENT_VISIT,
        )
        for employee_id, registered in StudentProfile.objects.values_list("employee_id", "registration_date")
        if registered and registered <= today and (employee_id, registered) not in visited
    ]
    Attendance.objects.bulk_create(missing, batch_size=500, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0010_rm_data_cleanup"),
        ("attendance", "0008_attendance_attendance_date_idx_and_more"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
