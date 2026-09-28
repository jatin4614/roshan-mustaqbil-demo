"""Seed a realistic, non-HR Roshan Mustaqbil demonstration dataset."""

from datetime import date, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from attendance.models import Attendance
from employee.models import Employee, StudentProfile


FIRST_NAMES = ("Aamir", "Ayesha", "Danish", "Sara", "Rahul", "Fatima", "Imran", "Mehak", "Arjun", "Zoya", "Kabir", "Ira", "Rohan", "Nisha", "Farhan")
LAST_NAMES = ("Ahmad", "Khan", "Sharma", "Bhat", "Singh", "Verma", "Mir", "Patel", "Kaur", "Nair")
GOALS = ("Defence", "UPSC / Civil Services", "NEET UG", "NEET PG", "Other")
PURPOSES = tuple(item[0] for item in StudentProfile.PURPOSES)
REQUIREMENTS = StudentProfile.REQUIREMENT_CHOICES[:-1]


class Command(BaseCommand):
    help = "Create 960 RM student records with realistic active, dormant and inactive attendance."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=960)

    @transaction.atomic
    def handle(self, *args, **options):
        count, today = options["count"], date.today()
        existing = {student.email: student for student in Employee.objects.filter(email__endswith="@rm.demo")}
        new_students = []
        for number in range(1, count + 1):
            registration = f"YC-{number:04d}"
            email = f"{registration.lower()}@rm.demo"
            first, last = FIRST_NAMES[(number - 1) % len(FIRST_NAMES)], LAST_NAMES[(number * 3) % len(LAST_NAMES)]
            if email not in existing:
                new_students.append(Employee(email=email, employee_first_name=first, employee_last_name=last, badge_id=registration, phone=f"7006{number:06d}", gender="female" if number % 2 else "male", dob=date(1997 + number % 13, number % 12 + 1, number % 27 + 1), qualification=("Class 12", "Bachelor's Degree", "Diploma", "Postgraduate")[number % 4], address=f"Area {number % 30 + 1}, Srinagar", is_active=True))
        Employee.objects.bulk_create(new_students, batch_size=200, ignore_conflicts=True)
        students = {student.email: student for student in Employee.objects.filter(email__endswith="@rm.demo")}
        profile_map = {profile.employee_id: profile for profile in StudentProfile.objects.filter(employee__email__endswith="@rm.demo")}
        profile_create, profile_update, attendance_create = [], [], []
        for number in range(1, count + 1):
            registration, email = f"YC-{number:04d}", f"yc-{number:04d}@rm.demo"
            student = students[email]
            student.badge_id, student.phone, student.is_active = registration, f"7006{number:06d}", True
            goal = GOALS[(number - 1) % len(GOALS)]
            profile = profile_map.get(student.id) or StudentProfile(employee=student)
            profile.career_goal = goal
            profile.defence_entry = ("NDA", "TES", "Other Entry Scheme")[number % 3] if goal == "Defence" else ""
            profile.purpose_of_rm = PURPOSES[number % len(PURPOSES)]
            profile.purpose_other = "Local support and guidance" if profile.purpose_of_rm == "Other" else ""
            profile.expectations = ("Quiet space for daily study.", "Access to books and mock tests.", "Career counselling and guidance.")[number % 3]
            profile.requirements = [REQUIREMENTS[number % len(REQUIREMENTS)], REQUIREMENTS[(number + 3) % len(REQUIREMENTS)]]
            profile.registration_date = today - timedelta(days=number % 720)
            profile.institution = ("Government Degree College", "Higher Secondary School", "Community College")[number % 3]
            profile.guardian_name, profile.guardian_phone = f"Guardian {first}", f"9900{number:06d}"
            profile.notes = "Demo registration for RM planning."
            profile.current_status = ("Studying at School / College", "Preparing from Home", "Preparing at Another Institute", "Employed", "Unable to Contact")[number % 5] if number > 210 else ""
            profile.inactivity_reason = "Follow-up required to understand current engagement." if number > 210 else ""
            (profile_update if profile.pk else profile_create).append(profile)
            if number <= 140:
                visit_days = [today - timedelta(days=offset) for offset in range(number % 5, 30, 6)]
            elif number <= 230:
                visit_days = [today - timedelta(days=31 + number % 30)]
            elif number <= 850:
                visit_days = [today - timedelta(days=61 + number % 300)]
            else:
                visit_days = []
            for visit_day in visit_days:
                attendance_create.append(Attendance(employee_id=student, attendance_date=visit_day, attendance_clock_in_date=visit_day, attendance_clock_in=time(9 + number % 4, number % 55), attendance_worked_hour="00:00", minimum_hour="00:00", request_description="Roshan Mustaqbil visit"))
        Employee.objects.bulk_update(students.values(), ["badge_id", "phone", "is_active"], batch_size=200)
        StudentProfile.objects.bulk_create(profile_create, batch_size=200)
        StudentProfile.objects.bulk_update(profile_update, ["career_goal", "defence_entry", "purpose_of_rm", "purpose_other", "expectations", "requirements", "registration_date", "institution", "guardian_name", "guardian_phone", "notes", "current_status", "inactivity_reason"], batch_size=200)
        Attendance.objects.bulk_create(attendance_create, batch_size=500, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"RM demo data ready: {count} registered students ({len(new_students)} new), with visit history."))
