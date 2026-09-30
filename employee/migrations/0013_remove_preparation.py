"""Preparation tracking (stage and exam year) is no longer recorded: a
student's progress is followed through attendance, their goal and
follow-up calls."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0012_rm_enrollment_visit_labels"),
    ]

    operations = [
        migrations.RemoveField(model_name="studentprofile", name="prep_stage"),
        migrations.RemoveField(model_name="studentprofile", name="target_year"),
    ]
