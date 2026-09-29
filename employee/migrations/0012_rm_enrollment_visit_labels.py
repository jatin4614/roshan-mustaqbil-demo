"""Label the enrollment visit for students who were marked present on the
day they enrolled before enrolling itself counted as a visit.

Migration 0011 added a visit for students with none on their enrollment
day, but left existing visits on that day as ordinary visits. Label those as
the enrollment visit, so every student has exactly one. Also fill in the
weekday on centre visits created in bulk (imports, 0011), which skipped the
model's save().
"""

from django.db import migrations, models
from django.utils import timezone

ENROLLMENT_VISIT = "Enrolled at the centre"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def forwards(apps, schema_editor):
    StudentProfile = apps.get_model("employee", "StudentProfile")
    Attendance = apps.get_model("attendance", "Attendance")
    EmployeeShiftDay = apps.get_model("base", "EmployeeShiftDay")

    labelled = set(
        Attendance.objects.filter(request_description=ENROLLMENT_VISIT, employee_id__rm_profile__isnull=False)
        .values_list("employee_id", flat=True)
    )
    for employee_id, registered in StudentProfile.objects.values_list("employee_id", "registration_date"):
        if employee_id in labelled or not registered:
            continue
        Attendance.objects.filter(employee_id=employee_id, attendance_date=registered).update(request_description=ENROLLMENT_VISIT)

    days = {day.day: day.pk for day in EmployeeShiftDay.objects.all()}
    missing = Attendance.objects.filter(employee_id__rm_profile__isnull=False, attendance_day__isnull=True)
    for index, name in enumerate(WEEKDAYS):
        if name not in days:
            continue
        # Django's week_day lookup counts Sunday as 1.
        missing.filter(attendance_date__week_day=(index + 1) % 7 + 1).update(attendance_day_id=days[name])


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0011_rm_enrollment_visits"),
        ("base", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="studentprofile",
            name="registration_date",
            field=models.DateField(default=timezone.localdate),
        ),
    ]
