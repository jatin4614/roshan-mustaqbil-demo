"""Roshan Mustaqbil centre screens: access, enrollment, lists, the attendance
desk, follow-up calls, imports and the demo seed."""

import importlib
import os
from datetime import time, timedelta

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance
from base import rm_charts
from base.rm import (
    ENROLLMENT_VISIT, REGULAR_VISIT, check_out, clear_check_out, engagement_q, engagement_status, in_centre_now,
    is_centre_admin, is_new_no_return, is_no_return, mark_student_present, needs_call, needs_call_q, no_return_q,
    normalize_phone, normalize_qualification, record_followup, stay_minutes, student_queryset, valid_mobile,
    with_last_visit,
)
from base.rm_common import PAGE_SIZE
from base.rm_students import StudentRegistrationForm, queue_counts, queue_students
from employee.models import Employee, EmployeeWorkInformation, StudentFollowUp, StudentProfile
from horilla.testkit.factories import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser

cleanup = importlib.import_module("employee.migrations.0010_rm_data_cleanup")


def at_three_pm(test):
    """Pin "now" to 3 pm today (the check-in/out tests back-date times)."""
    from unittest import mock

    real = timezone.localtime

    def fake(value=None, *args, **kwargs):
        if value is not None:
            return real(value, *args, **kwargs)
        return real().replace(hour=15, minute=0, second=0, microsecond=0)

    return mock.patch("django.utils.timezone.localtime", fake)(test)
enrollment_visits = importlib.import_module("employee.migrations.0011_rm_enrollment_visits")
enrollment_labels = importlib.import_module("employee.migrations.0012_rm_enrollment_visit_labels")


class HelperTests(SimpleTestCase):
    def test_nice_scale_rounds_up_to_a_clean_step(self):
        self.assertEqual(rm_charts.nice_scale(57), (60, [0, 20, 40, 60]))
        self.assertEqual(rm_charts.nice_scale(405)[0], 500)
        self.assertEqual(rm_charts.nice_scale(0)[0], 4)

    def test_fold_tail_keeps_the_largest_and_sums_the_rest(self):
        folded = rm_charts.fold_tail({"a": 10, "b": 8, "c": 3, "d": 2, "e": 1}, 3, other="Rest")
        self.assertEqual(folded, {"a": 10, "b": 8, "Rest": 6})

    def test_catch_all_buckets_sort_last(self):
        rows = rm_charts.bars({"Other outcomes": 50, "Employed": 10, "Studying": 20})
        self.assertEqual([row["label"] for row in rows], ["Studying", "Employed", "Other outcomes"])

    def test_line_chart_spans_the_width(self):
        chart = rm_charts.line([{"label": "", "tip": "", "value": value} for value in (10, 20, 15)])
        self.assertTrue(chart["path"].startswith("M0.0,"))
        self.assertEqual([point["left"] for point in chart["items"]], [0, 50, 100])
        self.assertTrue(chart["items"][-1]["last"])

    def test_median(self):
        self.assertEqual(rm_charts.median([1, 9, 3]), 3)
        self.assertEqual(rm_charts.median([1, 2, 3, 4]), 2.5)

    def test_phone_numbers_are_stored_as_ten_digits(self):
        self.assertEqual(normalize_phone("+91 94190-12345"), "9419012345")
        self.assertEqual(normalize_phone("09419012345"), "9419012345")
        self.assertTrue(valid_mobile("9419012345"))
        self.assertFalse(valid_mobile("call later"))

    def test_qualifications_map_onto_the_fixed_list(self):
        self.assertEqual(normalize_qualification("12th pass"), "Class 12")
        self.assertEqual(normalize_qualification("B.Sc"), "Bachelor's Degree")
        self.assertEqual(normalize_qualification("M.A. Urdu"), "Postgraduate")
        self.assertEqual(cleanup.locality_from("Tangdar, near bridge"), "Karnah")

    def test_didnt_come_back_after_enrolling(self):
        today = timezone.localdate()
        enrolled = today - timedelta(days=10)
        self.assertTrue(is_no_return(enrolled, enrolled, "Active", today))
        self.assertFalse(is_no_return(today - timedelta(days=2), enrolled, "Active", today))  # came back
        self.assertFalse(is_no_return(today - timedelta(days=3), today - timedelta(days=3), "Active", today))  # too soon to tell
        self.assertFalse(is_no_return(enrolled, enrolled, "Moved On", today))

    def test_enrolling_counts_as_a_visit(self):
        today = timezone.localdate()
        # No attendance record at all: the enrollment date still counts.
        self.assertEqual(engagement_status(None, today, "", today - timedelta(days=5)), "Active")
        self.assertEqual(engagement_status(None, today, "", today - timedelta(days=90)), "Inactive")
        # A visit before the enrollment date never makes them look older.
        self.assertEqual(engagement_status(today - timedelta(days=90), today, "", today - timedelta(days=5)), "Active")

    def test_the_first_call_list_is_for_recent_enrollees(self):
        today = timezone.localdate()
        recent, old = today - timedelta(days=20), today - timedelta(days=200)
        self.assertTrue(is_new_no_return(recent, recent, "Active", today))
        self.assertFalse(is_new_no_return(old, old, "Inactive", today))
        self.assertTrue(is_no_return(old, old, "Inactive", today))  # still didn't come back

    def test_needs_call_rules(self):
        today = timezone.localdate()
        profile = {"last_followup_date": None, "next_call_date": None, "current_status": "", "registration_date": today - timedelta(days=200)}
        self.assertTrue(needs_call("Inactive", today - timedelta(days=90), profile, today))
        self.assertFalse(needs_call("Active", today, profile, today))
        reached = {**profile, "last_followup_date": today - timedelta(days=3), "current_status": "Employed"}
        self.assertFalse(needs_call("Inactive", today - timedelta(days=90), reached, today))
        unreachable = {**profile, "last_followup_date": today - timedelta(days=8), "current_status": "Unable to Contact"}
        self.assertTrue(needs_call("Inactive", today - timedelta(days=90), unreachable, today))
        planned = {**reached, "next_call_date": today}
        self.assertTrue(needs_call("Dormant", today - timedelta(days=40), planned, today))


class RegistrationFormTests(SimpleTestCase):
    def test_each_field_is_rendered_once(self):
        names = [row["field"].name for section in StudentRegistrationForm().sections() for row in section["rows"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names) | {"confirm_new"}, set(StudentRegistrationForm.base_fields))

    def _form(self, **values):
        data = {"full_name": "Asma Lone", "phone": "94190 12345", "gender": "female", "age": "19", **values}
        return StudentRegistrationForm(data=data)

    def test_phone_is_cleaned_and_checked(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "9419012345")
        self.assertIn("phone", self._form(phone="12345").errors)

    def test_date_of_birth_or_age_is_needed(self):
        self.assertIn("dob", self._form(age="").errors)
        future = (timezone.localdate() + timedelta(days=5)).isoformat()
        self.assertIn("dob", self._form(dob=future).errors)

    def test_goal_details_are_required_where_they_apply(self):
        self.assertIn("defence_entry", self._form(career_goal="Defence").errors)
        self.assertIn("goal_detail", self._form(career_goal="Other").errors)
        self.assertNotIn("goal_detail", self._form(career_goal="Other", target_exam="JEE").errors)


@override_settings(ALLOWED_HOSTS=["testserver"])
class CentreScreensTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Roshan Mustaqbil")
        cls.today = timezone.localdate()
        cls.admin = make_user("centre-admin", is_superuser=True)
        make_employee(company=cls.company, email="admin@test.rm", user=cls.admin)
        cls.nobody = make_user("nobody")
        make_employee(company=cls.company, email="nobody@test.rm", user=cls.nobody)
        students = [
            Employee(employee_first_name=f"Student{index:02d}", employee_last_name="Dar", email=f"s{index}@rm.test",
                     phone=f"94190000{index:02d}", badge_id=f"TS-{index:04d}", gender="female" if index % 2 else "male",
                     dob=cls.today.replace(year=cls.today.year - 19), is_active=True)
            for index in range(PAGE_SIZE + 5)
        ]
        Employee.objects.bulk_create(students)
        cls.students = list(Employee.objects.filter(email__endswith="@rm.test").order_by("badge_id"))
        # Everyone enrolled 90 days ago; most have no attendance records at
        # all (older data), so their enrollment date is their only visit.
        StudentProfile.objects.bulk_create([
            StudentProfile(employee=student, career_goal="Defence" if index % 3 == 0 else "NEET UG", registration_date=cls.today - timedelta(days=90),
                           locality="Handwara" if index % 2 else "Kupwara", requirements=["Mock Tests"] if index % 4 == 0 else ["Study Space"])
            for index, student in enumerate(cls.students)
        ])
        # 0: active, 1: slipping away, 2: inactive, everyone else: only came to enroll
        for student, days_ago in zip(cls.students, (2, 45, 80)):
            day = cls.today - timedelta(days=days_ago)
            Attendance.objects.bulk_create([Attendance(employee_id=student, attendance_date=day, attendance_clock_in_date=day, attendance_clock_in=time(10), attendance_worked_hour="00:00", minimum_hour="00:00")])

    def setUp(self):
        self.client.force_login(self.admin)
        cache.clear()  # the desk remembers recent check-backs-in there

    def _profile(self, index):
        return StudentProfile.objects.get(employee=self.students[index])

    # ── Access ─────────────────────────────────────────────────────────

    def test_the_administrator_is_the_only_sign_in(self):
        self.assertTrue(is_centre_admin(self.admin))
        self.assertFalse(is_centre_admin(HorillaUser.objects.get(pk=self.nobody.pk)))
        self.assertRedirects(self.client.get(reverse("rm-home")), reverse("dashboard"), fetch_redirect_response=False)
        self.client.force_login(self.nobody)
        for name in ("dashboard", "youth-daily-attendance", "rm-students", "rm-calls", "rm-import"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_bootstrap_leaves_one_account(self):
        old = make_user("desk", email="desk@staff.rm.local")
        call_command("bootstrap_roshan_mustaqbil_demo", password="Kupwara#2026", username="centre-admin", stdout=open(os.devnull, "w"))
        self.assertFalse(HorillaUser.objects.filter(pk=old.pk, is_active=True).exists())
        self.assertTrue(HorillaUser.objects.get(pk=self.admin.pk).is_active)

    # ── Engagement, lists and exports ──────────────────────────────────

    def test_database_engagement_filter_matches_the_python_rule(self):
        profile = self._profile(3)
        profile.outcome = "Selected"
        profile.save()
        annotated = list(with_last_visit(student_queryset(), self.today))
        for status in ("Active", "Dormant", "Inactive", "Moved On"):
            via_db = set(with_last_visit(student_queryset(), self.today).filter(engagement_q(status, self.today)).values_list("id", flat=True))
            via_python = {row.id for row in annotated if engagement_status(row.last_visit, self.today, row.rm_profile.outcome) == status}
            self.assertEqual(via_db, via_python, status)
        via_db = set(with_last_visit(student_queryset(), self.today).filter(no_return_q(self.today)).values_list("id", flat=True))
        via_python = {row.id for row in annotated if is_no_return(row.last_visit, row.rm_profile.registration_date, engagement_status(row.last_visit, self.today, row.rm_profile.outcome), self.today)}
        self.assertEqual(via_db, via_python)
        self.assertEqual(len(via_db), len(self.students) - 4)  # all but the three who came back and the moved-on one

    def test_student_list_is_paginated_and_keeps_filters(self):
        response = self.client.get(reverse("rm-students"))
        self.assertEqual(len(response.context["rows"]), PAGE_SIZE)
        response = self.client.get(reverse("rm-students"), {"engagement": "Active", "goal": "Defence"})
        self.assertEqual([row["student"] for row in response.context["rows"]], [self.students[0]])
        self.assertContains(response, '<option value="Active" selected>', html=False)

    def test_new_filters(self):
        response = self.client.get(reverse("rm-students"), {"requirement": "Mock Tests"})
        self.assertEqual(response.context["page"].paginator.count, len([s for i, s in enumerate(self.students) if i % 4 == 0]))
        response = self.client.get(reverse("rm-students"), {"locality": "Handwara", "engagement": "Dormant"})
        self.assertEqual([row["student"] for row in response.context["rows"]], [self.students[1]])
        due = self.client.get(reverse("rm-students"), {"call": "due"}).context["page"].paginator.count
        self.assertEqual(due, len(self.students) - 1)  # everyone but the active student

    def test_csv_export_opens_cleanly_in_excel(self):
        response = self.client.get(reverse("rm-students"), {"engagement": "Dormant", "export": "csv"})
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))
        lines = text.strip().splitlines()
        self.assertIn("Guardian phone", lines[0])
        self.assertEqual(len(lines), 2)

    # ── Enrollment ─────────────────────────────────────────────────────

    def _enroll(self, **extra):
        data = {"full_name": "Iqra Wani", "phone": "9419123456", "gender": "female", "age": "18", "career_goal": "NEET UG",
                "requirements": ["Study Space", "Mock Tests"], "registration_date": self.today.isoformat(), **extra}
        return self.client.post(reverse("rm-enroll-student") + extra.pop("query", ""), data)

    def test_enrolling_keeps_the_phone_and_creates_no_login(self):
        response = self._enroll()
        student = Employee.objects.get(employee_first_name="Iqra")
        self.assertRedirects(response, reverse("rm-student-profile", args=[student.id]), fetch_redirect_response=False)
        self.assertEqual(student.phone, "9419123456")
        self.assertIsNone(student.employee_user_id)
        self.assertEqual(student.dob.year, self.today.year - 18)
        # No HR work record, and so no payroll contract: students aren't staff.
        self.assertFalse(EmployeeWorkInformation.objects.filter(employee_id=student).exists())

    def test_enrolling_marks_the_student_present(self):
        # Students enroll in person, wherever the form is opened from.
        response = self._enroll()
        student = Employee.objects.get(employee_first_name="Iqra")
        visit = Attendance.objects.get(employee_id=student)
        self.assertEqual((visit.attendance_date, visit.request_description), (self.today, ENROLLMENT_VISIT))
        self.assertIsNotNone(visit.attendance_clock_in)
        self.assertIsNone(visit.attendance_clock_out)
        self.assertIn("and checked in at", str(list(response.wsgi_request._messages)[0]))

    def test_an_older_paper_registration_records_that_day(self):
        earlier = self.today - timedelta(days=200)
        self._enroll(registration_date=earlier.isoformat())
        student = Employee.objects.get(employee_first_name="Iqra")
        visit = Attendance.objects.get(employee_id=student)
        self.assertEqual(visit.attendance_date, earlier)
        self.assertIsNone(visit.attendance_clock_in)
        # Correcting the enrollment date moves the enrollment visit with it.
        corrected = earlier - timedelta(days=20)
        self.client.post(reverse("rm-edit-student", args=[student.id]), {
            "full_name": "Iqra Wani", "phone": "9419123456", "gender": "female", "age": "18", "registration_date": corrected.isoformat(),
        })
        self.assertEqual(list(Attendance.objects.filter(employee_id=student).values_list("attendance_date", flat=True)), [corrected])

    def test_moving_the_enrollment_date_onto_a_day_with_a_visit(self):
        earlier = self.today - timedelta(days=200)
        self._enroll(registration_date=earlier.isoformat())
        student = Employee.objects.get(employee_first_name="Iqra")
        visited = self.today - timedelta(days=150)
        mark_student_present(student, day=visited)
        self.client.post(reverse("rm-edit-student", args=[student.id]), {
            "full_name": "Iqra Wani", "phone": "9419123456", "gender": "female", "age": "18", "registration_date": visited.isoformat(),
        })
        visits = Attendance.objects.filter(employee_id=student)
        self.assertEqual(list(visits.values_list("attendance_date", "request_description")), [(visited, ENROLLMENT_VISIT)])

    def test_an_enrollment_visit_cant_be_removed_on_its_own(self):
        self._enroll()
        student = Employee.objects.get(employee_first_name="Iqra")
        visit = Attendance.objects.get(employee_id=student)
        self.client.post(reverse("rm-undo-checkin"), {"record_id": visit.id}, HTTP_HX_REQUEST="true")
        self.client.post(reverse("rm-remove-visit", args=[visit.id]))
        self.assertTrue(Attendance.objects.filter(id=visit.id).exists())
        self.assertContains(self.client.get(reverse("rm-remove-visit", args=[visit.id])), "Correct the enrollment date")
        # An ordinary visit can be removed.
        record, _ = mark_student_present(self.students[16])
        self.assertContains(self.client.post(reverse("rm-undo-checkin"), {"record_id": record.id}, HTTP_HX_REQUEST="true"), "Removed the visit")

    def test_removing_a_student_enrolled_by_mistake(self):
        self._enroll()
        student = Employee.objects.get(employee_first_name="Iqra")
        self.assertContains(self.client.get(reverse("rm-remove-student", args=[student.id])), "1 visit")
        self.assertRedirects(self.client.post(reverse("rm-remove-student", args=[student.id])), reverse("rm-students"), fetch_redirect_response=False)
        self.assertFalse(Employee.objects.filter(id=student.id).exists())  # gone, not just hidden
        self.assertFalse(Attendance.objects.filter(employee_id=student.id).exists())

    def test_migration_adds_missing_enrollment_visits(self):
        from django.apps import apps

        enrollment_visits.forwards(apps, None)
        for student in self.students:
            self.assertTrue(Attendance.objects.filter(employee_id=student, attendance_date=self.today - timedelta(days=90)).exists())

    def test_migration_labels_a_visit_already_on_the_enrollment_day(self):
        from django.apps import apps

        enrolled = self.today - timedelta(days=90)
        day_one = Attendance.objects.create(
            employee_id=self.students[40], attendance_date=enrolled, attendance_clock_in_date=enrolled,
            attendance_worked_hour="00:00", minimum_hour="00:00", request_description=REGULAR_VISIT,
        )
        enrollment_visits.forwards(apps, None)
        enrollment_labels.forwards(apps, None)
        day_one.refresh_from_db()
        self.assertEqual(day_one.request_description, ENROLLMENT_VISIT)
        self.assertFalse(Attendance.objects.filter(employee_id__rm_profile__isnull=False, attendance_day__isnull=True).exists())

    def test_possible_duplicates_are_flagged_before_enrolling(self):
        response = self._enroll(phone=self.students[5].phone)
        self.assertContains(response, "already enrolled")
        self.assertFalse(Employee.objects.filter(employee_first_name="Iqra").exists())
        self._enroll(phone=self.students[5].phone, confirm_new="on")
        self.assertTrue(Employee.objects.filter(employee_first_name="Iqra").exists())

    def test_enrolling_from_the_desk_marks_present(self):
        response = self.client.post(reverse("rm-enroll-student") + "?next=desk", {
            "full_name": "Bisma Mir", "phone": "9419777777", "gender": "female", "age": "17", "next": "desk",
        })
        self.assertRedirects(response, reverse("youth-daily-attendance"), fetch_redirect_response=False)
        student = Employee.objects.get(employee_first_name="Bisma")
        self.assertTrue(Attendance.objects.filter(employee_id=student, attendance_date=self.today).exists())

    # ── Attendance desk ────────────────────────────────────────────────

    def test_enter_marks_only_a_unique_exact_match(self):
        url, headers = reverse("youth-daily-attendance"), {"HTTP_HX_REQUEST": "true"}
        student = self.students[10]
        response = self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers)
        self.assertContains(response, "is checked in at")
        # A second Enter straight away is a double press, not leaving.
        self.assertContains(self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers), "just now. Nothing changed.")
        self.assertEqual(Attendance.objects.filter(employee_id=student, attendance_date=self.today).count(), 1)
        # A partial match is listed, never marked.
        self.client.get(url, {"q": "Student11", "mark_exact": "1"}, **headers)
        self.assertFalse(Attendance.objects.filter(employee_id=self.students[11], attendance_date=self.today).exists())

    def test_typing_never_marks_a_student(self):
        # Requests sent while typing come from the search box itself.
        student = self.students[12]
        self.client.get(reverse("youth-daily-attendance"), {"q": student.badge_id, "mark_exact": "1"}, HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="rm-desk-search")
        self.assertFalse(Attendance.objects.filter(employee_id=student, attendance_date=self.today).exists())

    def test_a_shared_phone_lists_everyone_on_it(self):
        Employee.objects.filter(pk=self.students[13].pk).update(phone=self.students[12].phone)
        response = self.client.get(reverse("youth-daily-attendance"), {"q": self.students[12].phone, "mark_exact": "1"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "2 students share this number")
        self.assertFalse(Attendance.objects.filter(employee_id__in=self.students[12:14], attendance_date=self.today).exists())

    def test_back_dated_visits_from_a_paper_register(self):
        day = self.today - timedelta(days=3)
        self.client.post(reverse("youth-daily-attendance"), {"student_id": self.students[14].id, "on": day.isoformat()})
        record = Attendance.objects.get(employee_id=self.students[14], attendance_date=day)
        self.assertIsNone(record.attendance_clock_in)
        too_old = (self.today - timedelta(days=45)).isoformat()
        self.client.post(reverse("youth-daily-attendance"), {"student_id": self.students[15].id, "on": too_old})
        self.assertTrue(Attendance.objects.filter(employee_id=self.students[15], attendance_date=self.today).exists())

    # ── Check-in and check-out ─────────────────────────────────────────

    def _checked_in(self, student, minutes_ago):
        """Check a student in, back-dating the check-in time today (the
        clock is pinned to 3 pm by at_three_pm, so this never crosses midnight)."""
        from datetime import datetime

        record, _ = mark_student_present(student)
        arrived = (datetime.combine(self.today, timezone.localtime().time()) - timedelta(minutes=minutes_ago)).time().replace(second=0, microsecond=0)
        Attendance.objects.filter(pk=record.pk).update(attendance_clock_in=arrived)
        record.refresh_from_db()
        return record

    @at_three_pm
    def test_enter_checks_in_then_out_then_back_in(self):
        url, headers = reverse("youth-daily-attendance"), {"HTTP_HX_REQUEST": "true"}
        student = self.students[33]
        record = self._checked_in(student, minutes_ago=150)
        response = self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers)
        self.assertContains(response, "is checked out at")
        self.assertContains(response, "after 2 h 30 min")
        record.refresh_from_db()
        self.assertIsNotNone(record.attendance_clock_out)
        self.assertEqual(stay_minutes(record), 150)
        # A double press straight after checking out doesn't check them back in.
        self.assertContains(self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers), "just now. Nothing changed.")
        record.refresh_from_db()
        self.assertIsNotNone(record.attendance_clock_out)
        # Back an hour later: Enter checks them in again, still one visit for the day.
        Attendance.objects.filter(pk=record.pk).update(attendance_clock_out=time(14, 0))
        response = self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers)
        self.assertContains(response, "is back in the centre")
        self.assertContains(response, 'name="previous_out" value="14:00"')
        record.refresh_from_db()
        self.assertIsNone(record.attendance_clock_out)
        self.assertEqual(Attendance.objects.filter(employee_id=student, attendance_date=self.today).count(), 1)
        # A double press straight after coming back doesn't check them out again.
        self.assertContains(self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers), "came back into the centre just now")
        record.refresh_from_db()
        self.assertIsNone(record.attendance_clock_out)

    @at_three_pm
    def test_undo_a_check_out_and_a_check_back_in(self):
        student = self.students[34]
        record = self._checked_in(student, minutes_ago=90)
        check_out(record)
        self.client.post(reverse("rm-undo-checkin"), {"record_id": record.id, "undo": "out"}, HTTP_HX_REQUEST="true")
        record.refresh_from_db()
        self.assertIsNone(record.attendance_clock_out)
        # Undo "back in": they're out again, at the time they had left.
        self.client.post(reverse("rm-undo-checkin"), {"record_id": record.id, "undo": "back", "previous_out": "14:30"}, HTTP_HX_REQUEST="true")
        record.refresh_from_db()
        self.assertEqual(record.attendance_clock_out, time(14, 30))

    @at_three_pm
    def test_desk_buttons_check_out_and_everyone_out(self):
        first, second = self._checked_in(self.students[35], 60), self._checked_in(self.students[36], 45)
        self.client.post(reverse("youth-daily-attendance"), {"student_id": self.students[35].id, "action": "out"}, HTTP_HX_REQUEST="true")
        first.refresh_from_db()
        self.assertIsNotNone(first.attendance_clock_out)
        self.assertEqual(list(in_centre_now()), [second])
        response = self.client.post(reverse("rm-check-out-everyone"), HTTP_HX_REQUEST="true")
        self.assertContains(response, "Checked out 1 student at")
        self.assertFalse(in_centre_now().exists())

    @at_three_pm
    def test_putting_back_a_visit_removed_by_mistake_keeps_its_times(self):
        student, headers = self.students[45], {"HTTP_HX_REQUEST": "true"}
        record = self._checked_in(student, minutes_ago=120)
        check_out(record, time(14, 30))
        removed = self.client.post(reverse("rm-undo-checkin"), {"record_id": record.id, "undo": "in"}, **headers)
        self.assertContains(removed, 'name="restore_in" value="13:00"')
        self.assertContains(removed, 'name="restore_out" value="14:30"')
        self.assertFalse(Attendance.objects.filter(employee_id=student, attendance_date=self.today).exists())
        back = self.client.post(reverse("youth-daily-attendance"), {"student_id": student.id, "action": "restore", "restore_in": "13:00", "restore_out": "14:30"}, **headers)
        self.assertContains(back, "visit is back, 1:00 PM to 2:30 PM.")
        record = Attendance.objects.get(employee_id=student, attendance_date=self.today)
        self.assertEqual((record.attendance_clock_in, record.attendance_clock_out, stay_minutes(record)), (time(13, 0), time(14, 30), 90))

    def test_correcting_a_visits_times(self):
        day = self.today - timedelta(days=2)
        record, _ = mark_student_present(self.students[37], day=day)
        url = reverse("rm-visit", args=[record.id])
        bad = self.client.post(url, {"action": "times", "checked_in": "15:00", "checked_out": "10:00"})
        self.assertContains(bad, "Check-out can&#x27;t be before check-in.")
        self.assertContains(self.client.post(url, {"action": "times", "checked_in": "06:00", "checked_out": "19:30"}), "more than 12 hours")
        self.client.post(url, {"action": "times", "checked_in": "10:15", "checked_out": "14:45"})
        record.refresh_from_db()
        self.assertEqual((record.attendance_clock_in, record.attendance_clock_out, stay_minutes(record)), (time(10, 15), time(14, 45), 270))
        self.assertEqual(record.attendance_worked_hour, "04:30")

    @at_three_pm
    def test_a_quick_check_out_is_never_before_the_check_in(self):
        student, url = self.students[38], reverse("youth-daily-attendance")
        self.client.post(url, {"student_id": student.id, "action": "in"}, HTTP_HX_REQUEST="true")
        self.client.post(url, {"student_id": student.id, "action": "out"}, HTTP_HX_REQUEST="true")
        record = Attendance.objects.get(employee_id=student, attendance_date=self.today)
        self.assertEqual(record.attendance_clock_out, record.attendance_clock_in)
        self.assertIsNone(stay_minutes(record))  # no time in the centre to count
        # The visit page accepts those times as they are.
        saved = self.client.post(reverse("rm-visit", args=[record.id]), {"action": "times", "checked_in": "15:00", "checked_out": "15:00"})
        self.assertEqual(saved.status_code, 302)

    @at_three_pm
    def test_undoing_a_check_in_brings_back_what_the_last_call_recorded(self):
        student, headers = self.students[39], {"HTTP_HX_REQUEST": "true"}
        record_followup(student.rm_profile, result="Joined Armed Forces / Selected", called_on=self.today - timedelta(days=10))
        self.client.get(reverse("youth-daily-attendance"), {"q": student.badge_id, "mark_exact": "1"}, **headers)
        self.assertEqual(StudentProfile.objects.get(employee=student).outcome, "")  # they came back
        record = Attendance.objects.get(employee_id=student, attendance_date=self.today)
        self.client.post(reverse("rm-undo-checkin"), {"record_id": record.id, "undo": "in"}, **headers)
        profile = StudentProfile.objects.get(employee=student)
        self.assertEqual((profile.outcome, profile.current_status), ("Selected", "Joined Armed Forces / Selected"))

    @at_three_pm
    def test_a_visit_without_a_time_today_gets_one_at_the_desk(self):
        student, url = self.students[44], reverse("youth-daily-attendance")
        record, _ = mark_student_present(student)
        Attendance.objects.filter(pk=record.pk).update(attendance_clock_in=None)  # imported for today, say
        self.assertEqual(self.client.get(url).context["untimed_count"], 1)
        response = self.client.post(url, {"student_id": student.id, "action": "in"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "without a time")
        record.refresh_from_db()
        self.assertEqual(record.attendance_clock_in, time(15, 0))

    def test_time_in_the_centre_on_the_dashboards(self):
        for index, (arrived, left) in enumerate(((time(9, 0), time(12, 0)), (time(10, 0), time(11, 0)), (time(14, 0), None))):
            day = self.today - timedelta(days=3)
            record, _ = mark_student_present(self.students[40 + index], day=day)
            Attendance.objects.filter(pk=record.pk).update(attendance_clock_in=arrived)
            record.refresh_from_db()
            if left:
                check_out(record, left)
        stay = self.client.get(reverse("dashboard")).context["stay"]
        # 4 visits with a check-in: these three plus the fixture's visit two
        # days ago, which has no check-out.
        self.assertEqual((stay["typical"], stay["count"], stay["timed"]), ("2 h 0 min", 2, 4))
        page = self.client.get(reverse("rm-attendance-dashboard"))
        self.assertContains(page, "Typical stay")
        self.assertContains(page, "How many are in the centre, hour by hour")

    def test_removing_an_older_visit(self):
        old = Attendance.objects.get(employee_id=self.students[2])
        self.client.post(reverse("rm-remove-visit", args=[old.id]))
        self.assertFalse(Attendance.objects.filter(id=old.id).exists())

    def test_a_returning_student_loses_their_stale_status(self):
        profile = self._profile(2)
        record_followup(profile, result="Joined Armed Forces / Selected", called_on=self.today - timedelta(days=5))
        profile.refresh_from_db()
        self.assertEqual(profile.outcome, "Selected")
        mark_student_present(self.students[2])
        profile.refresh_from_db()
        self.assertEqual((profile.outcome, profile.current_status), ("", ""))
        self.assertEqual(profile.followups.count(), 1)  # history is kept

    # ── Follow-up calls ────────────────────────────────────────────────

    def test_calls_build_a_history_and_leave_the_queue(self):
        profile = self._profile(20)
        record_followup(profile, result="Unable to Contact", called_on=self.today - timedelta(days=10))
        record_followup(profile, result="Employed", called_on=self.today - timedelta(days=2), notes="Works in Handwara")
        profile.refresh_from_db()
        self.assertEqual(profile.followups.count(), 2)
        self.assertEqual(profile.current_status, "Employed")
        due = with_last_visit(student_queryset(), self.today).filter(needs_call_q(self.today))
        self.assertFalse(due.filter(id=self.students[20].id).exists())

    def test_unreachable_students_come_back_after_a_week(self):
        profile = self._profile(21)
        record_followup(profile, result="Unable to Contact", called_on=self.today - timedelta(days=8))
        profile.refresh_from_db()
        self.assertEqual(profile.next_call_date, self.today - timedelta(days=1))
        due = with_last_visit(student_queryset(), self.today).filter(needs_call_q(self.today))
        self.assertTrue(due.filter(id=self.students[21].id).exists())

    def test_call_list_saves_and_moves_on(self):
        # A recent enrollee who hasn't been back: first on the first list.
        StudentProfile.objects.filter(employee=self.students[25]).update(registration_date=self.today - timedelta(days=20))
        page = self.client.get(reverse("rm-calls"), {"queue": "once"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "hasn't been back")
        student = page.context["rows"][0]["student"]
        self.assertEqual(student, self.students[25])
        response = self.client.post(reverse("rm-calls") + "?queue=once", {
            "student_id": student.id, f"s{student.id}-result": "Plans to Return", f"s{student.id}-called_on": self.today.isoformat(),
            f"s{student.id}-notes": "Will come on Monday",
        }, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Saved for")
        self.assertContains(response, 'id="rm-calls-due" hx-swap-oob="true"')  # the totals update too
        entry = StudentFollowUp.objects.get(student__employee=student)
        self.assertEqual(entry.created_by, self.admin)
        self.assertEqual(entry.next_call_date, self.today + timedelta(days=14))

    def test_older_students_who_never_came_back_are_on_the_inactive_list(self):
        once = {student.id for student in queue_students("once", self.today)}
        inactive = {student.id for student in queue_students("Inactive", self.today)}
        self.assertFalse(once)  # everyone enrolled 90 days ago
        self.assertIn(self.students[30].id, inactive)

    def test_waiting_for_a_call_is_the_same_everywhere(self):
        StudentProfile.objects.filter(employee=self.students[25]).update(registration_date=self.today - timedelta(days=20))
        total = sum(queue_counts(self.today).values())
        self.assertEqual(self.client.get(reverse("dashboard")).context["kpis"]["due"], total)
        self.assertEqual(self.client.get(reverse("rm-calls")).context["total_due"], total)
        sheet = self.client.get(reverse("rm-students"), {"call": "due", "export": "csv"}).content.decode("utf-8")
        self.assertEqual(len(sheet.strip().splitlines()) - 1, total)

    def test_profile_records_a_call(self):
        student = self.students[2]
        response = self.client.post(reverse("rm-student-profile", args=[student.id]), {
            "action": "follow_up", "result": "Employed", "called_on": self.today.isoformat(), "reason": "Works in Handwara", "notes": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._profile(2).current_status, "Employed")

    # ── Import ─────────────────────────────────────────────────────────

    def _upload(self, kind, text):
        url = reverse("rm-import")
        upload = SimpleUploadedFile("register.csv", text.encode("utf-8"), content_type="text/csv")
        self.client.post(url, {"kind": kind, "step": "check", "file": upload})
        return self.client.get(url, {"kind": kind, "preview": "1"})

    def test_importing_students_previews_then_creates_records(self):
        text = "full_name,phone,gender,dob,area,career_goal,exam,enrollment_date,support_needed\n"
        text += "Rafia Lone,94190 55555,F,2006-02-01,Handwara,Army,NDA,01-06-2024,Study Space; Books / Study Material; Sports\n"
        text += f"{self.students[3].get_full_name()},{self.students[3].phone},M,,,,,01-01-2024,\n"
        text += "No Phone,,F,,,,,01-01-2024,\n"
        text += "No Date,9419066666,F,,,,,,\n"
        preview = self._upload("students", text).context["preview"]
        self.assertEqual((preview["new"], preview["exists"], preview["errors"]), (1, 1, 2))
        self.client.post(reverse("rm-import"), {"kind": "students", "step": "confirm"})
        student = Employee.objects.get(employee_first_name="Rafia")
        profile = student.rm_profile
        self.assertEqual((student.phone, profile.career_goal, profile.defence_entry, profile.locality), ("9419055555", "Defence", "NDA", "Handwara"))
        self.assertEqual(profile.registration_date.isoformat(), "2024-06-01")
        self.assertEqual(profile.requirements, ["Study Space", "Books / Study Material", "Other"])
        self.assertIsNone(student.employee_user_id)
        # They came in to enroll: that day is their first visit.
        visit = Attendance.objects.get(employee_id=student)
        self.assertEqual((visit.attendance_date.isoformat(), visit.request_description), ("2024-06-01", ENROLLMENT_VISIT))

    def test_importing_past_attendance(self):
        day = (self.today - timedelta(days=60)).isoformat()
        before = (self.today - timedelta(days=100)).isoformat()  # before they enrolled
        text = (
            f"registration_number,phone,date,time,time_out\n{self.students[30].badge_id},,{day},10:15,13:45\n,{self.students[31].phone},{day},,\n"
            f"RM-9999,,{day},,\n{self.students[32].badge_id},,{before},,\n{self.students[33].badge_id},,{day},12:00,11:00\n"
            f"{self.students[34].badge_id},,{day},06:00,20:00\n"
        )
        # Student 31 had moved away, according to a call before the imported visit.
        record_followup(self.students[31].rm_profile, result="Moved / Relocated", called_on=self.today - timedelta(days=70))
        preview = self._upload("visits", text).context["preview"]
        self.assertEqual((preview["new"], preview["errors"]), (2, 4))
        self.client.post(reverse("rm-import"), {"kind": "visits", "step": "confirm"})
        imported = Attendance.objects.filter(employee_id__in=self.students[30:32], attendance_date=day)
        self.assertEqual(imported.count(), 2)
        self.assertEqual(stay_minutes(imported.get(employee_id=self.students[30])), 210)
        self.assertFalse(imported.filter(attendance_day__isnull=True).exists())
        self.assertEqual(StudentProfile.objects.get(employee=self.students[31]).outcome, "")  # they came back after that call

    # ── Demo seed ──────────────────────────────────────────────────────

    def test_top_up_never_creates_students(self):
        call_command("seed_youth_centre_demo", top_up=True, stdout=open(os.devnull, "w"))
        self.assertFalse(Employee.objects.filter(email__endswith="@rm.demo").exists())

    def test_reset_also_removes_students_added_during_a_demo(self):
        out = open(os.devnull, "w")
        call_command("seed_youth_centre_demo", count=12, stdout=out)
        demo = student_queryset().filter(email__endswith="@rm.demo")
        self.assertEqual(demo.count(), 12)
        # Every demo student has their enrollment visit, and none enrolled on a Sunday.
        for student in demo:
            self.assertTrue(Attendance.objects.filter(employee_id=student, request_description=ENROLLMENT_VISIT).exists())
            self.assertNotEqual(student.rm_profile.registration_date.weekday(), 6)
        # Demo visits from earlier days mostly have a check-out, always after the check-in.
        earlier = Attendance.objects.filter(employee_id__in=demo, attendance_date__lt=self.today, attendance_clock_in__isnull=False)
        self.assertGreater(earlier.filter(attendance_clock_out__isnull=False).count(), earlier.count() * 0.8)
        for visit in earlier.filter(attendance_clock_out__isnull=False):
            self.assertGreater(visit.attendance_clock_out, visit.attendance_clock_in)
        # Top-ups never undo the administrator's changes: a removed visit isn't
        # put back, and a cleared check-out isn't filled in again.
        removed = Attendance.objects.filter(employee_id__in=demo, request_description=REGULAR_VISIT).order_by("-attendance_date").first()
        removed_key = (removed.employee_id_id, removed.attendance_date)
        removed.delete()
        cleared = earlier.filter(attendance_clock_out__isnull=False).first()
        clear_check_out(cleared)
        call_command("seed_youth_centre_demo", top_up=True, stdout=out)
        self.assertFalse(Attendance.objects.filter(employee_id=removed_key[0], attendance_date=removed_key[1]).exists())
        cleared.refresh_from_db()
        self.assertIsNone(cleared.attendance_clock_out)
        self._enroll()  # a walk-in during the demo
        call_command("seed_youth_centre_demo", count=12, reset=True, stdout=out)
        self.assertFalse(Employee.objects.filter(employee_first_name="Iqra", is_active=True).exists())
        self.assertTrue(student_queryset().filter(id=self.students[0].id).exists())  # students from before the demo stay

    # ── Pages ──────────────────────────────────────────────────────────

    def test_bad_dates_in_links_do_not_break_history(self):
        self.assertEqual(self.client.get(reverse("youth-attendance-history"), {"date": "2026-02-30"}).status_code, 200)

    def test_dashboards_render(self):
        for name in ("dashboard", "rm-attendance-dashboard", "youth-centre-goals", "youth-centre-analytics", "youth-attendance-history", "rm-calls", "rm-import"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("youth-centre-analytics"), {"who": "all", "goal": "Defence"}).status_code, 200)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["current_total"], len(self.students))
        self.assertEqual(response.context["active"], 1)

    def test_recent_enrollees_are_too_early_to_tell(self):
        self._enroll()
        analytics = self.client.get(reverse("youth-centre-analytics"), {"who": "all"}).context
        this_month = analytics["enrollments"]["items"][-1]["parts"]
        self.assertEqual({part["key"]: part["value"] for part in this_month}["muted"], 1)
        kpis = self.client.get(reverse("dashboard")).context["kpis"]
        self.assertEqual((kpis["enrolled_too_early"], kpis["enrolled_month_back"]), (1, 0))
