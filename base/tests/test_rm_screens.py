"""Roshan Mustaqbil centre screens: roles, enrollment, lists, the attendance
desk, follow-up calls, imports and staff accounts."""

import importlib
from datetime import time, timedelta

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance
from base import rm_charts
from base.rm import (
    ROLE_GROUPS, engagement_q, engagement_status, mark_student_present, needs_call, needs_call_q,
    normalize_phone, normalize_qualification, record_followup, role_of, student_queryset, valid_mobile,
    with_last_visit,
)
from base.rm_common import PAGE_SIZE
from base.rm_students import StudentRegistrationForm
from employee.models import Employee, StudentFollowUp, StudentProfile
from horilla.testkit.factories import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser

cleanup = importlib.import_module("employee.migrations.0010_rm_data_cleanup")


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

    def test_needs_call_rules(self):
        today = timezone.localdate()
        profile = {"last_followup_date": None, "next_call_date": None, "current_status": ""}
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
        groups = {key: Group.objects.get_or_create(name=name)[0] for key, name in ROLE_GROUPS.items()}
        cls.manager = make_user("centre-manager", is_superuser=True)
        make_employee(company=cls.company, email="manager@test.rm", user=cls.manager)
        cls.coordinator = make_user("coordinator")
        make_employee(company=cls.company, email="coordinator@test.rm", user=cls.coordinator)
        cls.coordinator.groups.add(groups["coordinator"])
        cls.desk = make_user("desk")
        make_employee(company=cls.company, email="desk@test.rm", user=cls.desk)
        cls.desk.groups.add(groups["frontdesk"])
        cls.nobody = make_user("nobody")
        make_employee(company=cls.company, email="nobody@test.rm", user=cls.nobody)
        students = [
            Employee(employee_first_name=f"Student{index:02d}", employee_last_name="Dar", email=f"s{index}@rm.test",
                     phone=f"94190000{index:02d}", badge_id=f"RM-{index:04d}", gender="female" if index % 2 else "male",
                     dob=cls.today.replace(year=cls.today.year - 19), is_active=True)
            for index in range(PAGE_SIZE + 5)
        ]
        Employee.objects.bulk_create(students)
        cls.students = list(Employee.objects.filter(email__endswith="@rm.test").order_by("badge_id"))
        StudentProfile.objects.bulk_create([
            StudentProfile(employee=student, career_goal="Defence" if index % 3 == 0 else "NEET UG", registration_date=cls.today - timedelta(days=90),
                           locality="Handwara" if index % 2 else "Kupwara", requirements=["Mock Tests"] if index % 4 == 0 else ["Study Space"])
            for index, student in enumerate(cls.students)
        ])
        # 0: active, 1: slipping away, 2: inactive, everyone else: never came
        for student, days_ago in zip(cls.students, (2, 45, 120)):
            day = cls.today - timedelta(days=days_ago)
            Attendance.objects.bulk_create([Attendance(employee_id=student, attendance_date=day, attendance_clock_in_date=day, attendance_clock_in=time(10), attendance_worked_hour="00:00", minimum_hour="00:00")])

    def setUp(self):
        self.client.force_login(self.manager)

    def _profile(self, index):
        return StudentProfile.objects.get(employee=self.students[index])

    # ── Roles ──────────────────────────────────────────────────────────

    def test_roles_come_from_groups(self):
        self.assertEqual(role_of(self.manager), "manager")
        self.assertEqual(role_of(HorillaUser.objects.get(pk=self.coordinator.pk)), "coordinator")
        self.assertEqual(role_of(HorillaUser.objects.get(pk=self.desk.pk)), "frontdesk")
        self.assertIsNone(role_of(HorillaUser.objects.get(pk=self.nobody.pk)))

    def test_each_role_lands_on_its_own_screen(self):
        self.client.force_login(self.desk)
        self.assertRedirects(self.client.get(reverse("rm-home")), reverse("youth-daily-attendance"), fetch_redirect_response=False)
        self.client.force_login(self.coordinator)
        self.assertRedirects(self.client.get(reverse("rm-home")), reverse("dashboard"), fetch_redirect_response=False)
        self.client.force_login(self.nobody)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)

    def test_front_desk_can_mark_but_not_open_lists_or_staff(self):
        self.client.force_login(self.desk)
        self.assertEqual(self.client.get(reverse("youth-daily-attendance")).status_code, 200)
        self.assertEqual(self.client.get(reverse("rm-enroll-student")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("rm-students")), reverse("rm-home"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("rm-calls")), reverse("rm-home"), fetch_redirect_response=False)
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.get(reverse("rm-students")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("rm-staff")), reverse("rm-home"), fetch_redirect_response=False)

    # ── Engagement, lists and exports ──────────────────────────────────

    def test_database_engagement_filter_matches_the_python_rule(self):
        profile = self._profile(3)
        profile.outcome = "Selected"
        profile.save()
        annotated = list(with_last_visit(student_queryset(), self.today))
        for status in ("Active", "Dormant", "Inactive", "Never Attended", "Moved On"):
            via_db = set(with_last_visit(student_queryset(), self.today).filter(engagement_q(status, self.today)).values_list("id", flat=True))
            via_python = {row.id for row in annotated if engagement_status(row.last_visit, self.today, row.rm_profile.outcome) == status}
            self.assertEqual(via_db, via_python, status)

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

    def test_possible_duplicates_are_flagged_before_enrolling(self):
        response = self._enroll(phone=self.students[5].phone)
        self.assertContains(response, "already enrolled")
        self.assertFalse(Employee.objects.filter(employee_first_name="Iqra").exists())
        self._enroll(phone=self.students[5].phone, confirm_new="on")
        self.assertTrue(Employee.objects.filter(employee_first_name="Iqra").exists())

    def test_enrolling_from_the_desk_marks_present(self):
        self.client.force_login(self.desk)
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
        self.assertContains(self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers), "is marked present")
        self.assertContains(self.client.get(url, {"q": student.badge_id, "mark_exact": "1"}, **headers), "had already checked in")
        self.assertEqual(Attendance.objects.filter(employee_id=student, attendance_date=self.today).count(), 1)
        # A partial match is listed, never marked.
        self.client.get(url, {"q": "Student11", "mark_exact": "1"}, **headers)
        self.assertFalse(Attendance.objects.filter(employee_id=self.students[11], attendance_date=self.today).exists())

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

    def test_undo_and_remove_respect_roles(self):
        record, _ = mark_student_present(self.students[16])
        self.client.force_login(self.desk)
        self.assertContains(self.client.post(reverse("rm-undo-checkin"), {"record_id": record.id}, HTTP_HX_REQUEST="true"), "Removed the visit")
        old = Attendance.objects.get(employee_id=self.students[2])
        self.client.post(reverse("rm-remove-visit", args=[old.id]))
        self.assertTrue(Attendance.objects.filter(id=old.id).exists())  # front desk can't remove old visits
        self.client.force_login(self.coordinator)
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
        self.client.force_login(self.coordinator)
        page = self.client.get(reverse("rm-calls"), {"queue": "Never Attended"})
        self.assertEqual(page.status_code, 200)
        student = page.context["rows"][0]["student"]
        response = self.client.post(reverse("rm-calls") + "?queue=Never+Attended", {
            "student_id": student.id, f"s{student.id}-result": "Plans to Return", f"s{student.id}-called_on": self.today.isoformat(),
            f"s{student.id}-notes": "Will come on Monday",
        }, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Saved for")
        entry = StudentFollowUp.objects.get(student__employee=student)
        self.assertEqual(entry.created_by, self.coordinator)
        self.assertEqual(entry.next_call_date, self.today + timedelta(days=14))

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
        text += "Rafia Lone,94190 55555,F,2006-02-01,Handwara,Army,NDA,01-06-2024,Study Space; Mock Tests; Sports\n"
        text += f"{self.students[3].get_full_name()},{self.students[3].phone},M,,,,,,\n"
        text += "No Phone,,F,,,,,,\n"
        preview = self._upload("students", text).context["preview"]
        self.assertEqual((preview["new"], preview["exists"], preview["errors"]), (1, 1, 1))
        self.client.post(reverse("rm-import"), {"kind": "students", "step": "confirm"})
        student = Employee.objects.get(employee_first_name="Rafia")
        profile = student.rm_profile
        self.assertEqual((student.phone, profile.career_goal, profile.defence_entry, profile.locality), ("9419055555", "Defence", "NDA", "Handwara"))
        self.assertEqual(profile.registration_date.isoformat(), "2024-06-01")
        self.assertEqual(profile.requirements, ["Study Space", "Mock Tests", "Other"])
        self.assertIsNone(student.employee_user_id)

    def test_importing_past_attendance(self):
        day = (self.today - timedelta(days=100)).isoformat()
        text = f"registration_number,phone,date,time\n{self.students[30].badge_id},,{day},10:15\n,{self.students[31].phone},{day},\nRM-9999,,{day},\n"
        preview = self._upload("visits", text).context["preview"]
        self.assertEqual((preview["new"], preview["errors"]), (2, 1))
        self.client.post(reverse("rm-import"), {"kind": "visits", "step": "confirm"})
        self.assertEqual(Attendance.objects.filter(employee_id__in=self.students[30:32], attendance_date=day).count(), 2)

    # ── Staff ──────────────────────────────────────────────────────────

    def test_manager_adds_staff_who_must_choose_a_password(self):
        response = self.client.post(reverse("rm-staff"), {
            "full_name": "Asma Lone", "username": "asma", "phone": "9419000999", "role": "frontdesk", "password": "Kupwara#Desk2026",
        })
        self.assertRedirects(response, reverse("rm-staff"), fetch_redirect_response=False)
        user = HorillaUser.objects.get(username="asma")
        self.assertTrue(user.is_new_employee)
        self.assertEqual(role_of(user), "frontdesk")
        self.assertEqual(user.employee_get.get_full_name(), "Asma Lone")

    def test_staff_changes(self):
        coordinator = HorillaUser.objects.get(pk=self.coordinator.pk)
        self.client.post(reverse("rm-staff-update", args=[coordinator.id]), {"action": "role", "role": "manager"})
        self.assertEqual(role_of(HorillaUser.objects.get(pk=coordinator.pk)), "manager")
        self.client.post(reverse("rm-staff-update", args=[coordinator.id]), {"action": "deactivate"})
        self.assertFalse(HorillaUser.objects.get(pk=coordinator.pk).is_active)

    # ── Pages ──────────────────────────────────────────────────────────

    def test_bad_dates_in_links_do_not_break_history(self):
        self.assertEqual(self.client.get(reverse("youth-attendance-history"), {"date": "2026-02-30"}).status_code, 200)

    def test_dashboards_render(self):
        for name in ("dashboard", "rm-attendance-dashboard", "youth-centre-goals", "youth-centre-analytics", "youth-attendance-history", "rm-calls", "rm-import", "rm-staff"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("youth-centre-analytics"), {"who": "all", "goal": "Defence"}).status_code, 200)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["current_total"], len(self.students))
        self.assertEqual(response.context["active"], 1)
