"""Seed a realistic, non-HR Roshan Mustaqbil demonstration dataset.

Everything is derived from seeded random generators keyed on the student
number (and, for visits, the date), so a first run always produces the same
centre. Running it again later only tops up visits for students who are
still coming (and fills in the day so far); it never rewrites students,
profiles or follow-up calls that staff may have changed.

``--reset`` removes earlier demo students, their visits and calls first,
together with any students enrolled or imported in the app while the demo
data was loaded (a rehearsal's walk-ins and sample imports).
``--remove`` removes all of those and stops, for going live with real data.
"""

import random
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max, Min, Q
from django.utils import timezone

from attendance.models import Attendance
from base.models import EmployeeShiftDay
from base.rm import CALL_BACK_AFTER_DAYS, ENROLLMENT_VISIT, REGULAR_VISIT, delete_students
from employee.models import Employee, StudentFollowUp, StudentProfile

DEMO_DOMAINS = ("@rm.demo", "@roshanmustaqbil.demo")
# Students enrolled or imported in the app get this address.
APP_DOMAIN = "@rm.local"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

MALE = ("Aadil", "Aamir", "Adnan", "Aijaz", "Arif", "Asif", "Bilal", "Danish", "Faisal", "Farhan", "Firdous", "Haris", "Irfan", "Ishfaq", "Javid", "Junaid", "Mudasir", "Mushtaq", "Nasir", "Owais", "Parvaiz", "Rayees", "Sajad", "Sameer", "Showkat", "Suhail", "Tanveer", "Tariq", "Umar", "Waseem", "Yasir", "Zahid", "Zubair", "Aqib", "Basit", "Mehraj", "Shahid", "Rizwan", "Imtiyaz", "Hilal")
FEMALE = ("Aafreen", "Afshana", "Aiman", "Arifa", "Asma", "Bisma", "Heena", "Iqra", "Insha", "Mehvish", "Mehak", "Nadiya", "Nazia", "Nusrat", "Rafia", "Rubeena", "Rukhsana", "Sadaf", "Saima", "Shabnam", "Shazia", "Suhaila", "Tabassum", "Uzma", "Zainab", "Zoya", "Sana", "Mariya", "Tahira", "Rabia")
SURNAMES = ("Bhat", "Dar", "Lone", "Mir", "Wani", "Sheikh", "Khan", "Malik", "Peer", "Shah", "Rather", "Ganie", "Qureshi", "Mughal", "Hajam", "Sofi", "Parray", "Najar", "Tantray", "Chalkoo", "Bhat", "Dar", "Lone", "Mir", "Wani")
# Tehsils (weighted by distance from the centre) and a few villages in each.
TEHSILS = (
    ("Kupwara", 22, ("Kupwara town", "Batpora", "Darpora", "Bumhama")), ("Handwara", 16, ("Handwara", "Wadipora", "Nowgam")),
    ("Trehgam", 9, ("Trehgam", "Dardpora")), ("Kralpora", 7, ("Kralpora", "Chandigam")), ("Lolab", 7, ("Lalpora", "Kalaroos road")),
    ("Sogam", 5, ("Sogam",)), ("Villgam", 5, ("Villgam", "Hayhama")), ("Drugmulla", 5, ("Drugmulla", "Bohipora")),
    ("Kalaroos", 4, ("Kalaroos",)), ("Karnah", 3, ("Tangdar", "Chitterkote")), ("Langate", 5, ("Langate", "Mawar")),
    ("Qalamabad", 3, ("Qalamabad",)), ("Rajwar", 2, ("Rajwar",)), ("Zachaldara", 2, ("Zachaldara",)),
    ("Magam", 2, ("Magam",)), ("Chowkibal", 2, ("Chowkibal",)), ("Machil", 1, ("Machil",)), ("Keran", 1, ("Keran",)),
)
EXPECTATIONS = (
    "A quiet place to study every day.",
    "Mock tests and guidance for the written exam.",
    "Help choosing the right career path.",
    "Books and study material I cannot afford.",
    "Reliable internet for online classes and forms.",
    "Someone to talk to about exam stress.",
    "Physical training tips and interview practice.",
    "Computer practice for online exams.",
    "Guidance on filling application forms on time.",
    "A senior who has cleared the exam to mentor me.",
)
REASONS = {
    "Studying at School / College": "Classes clash with centre hours.",
    "Preparing from Home": "Travel from the village is difficult.",
    "Preparing at Another Institute": "Joined a coaching institute in Srinagar.",
    "Plans to Return": "Was unwell for a few weeks.",
    "Employed": "Took up a job to support the family.",
    "Joined Armed Forces / Selected": "Selected, now in training.",
    "Joined Professional Course": "Admitted to a degree programme outside the district.",
    "Moved / Relocated": "Family moved out of Kupwara.",
    "No Longer Interested": "Lost interest in the exam.",
    "Unable to Contact": "",
    "Wrong Number": "",
    "Other": "Personal reasons.",
}
NOTES = {
    "Unable to Contact": "Phone switched off; try the guardian.",
    "Wrong Number": "Number belongs to someone else; ask at the next visit to the village.",
    "Plans to Return": "Said they'll come back next week.",
}
STATUS_OUTCOMES = StudentProfile.STATUS_OUTCOMES


def pick(rng, weighted):
    """weighted: sequence of (value, weight)."""
    values, weights = zip(*weighted)
    return rng.choices(values, weights=weights, k=1)[0]


def age_band_dob(rng, today):
    age = pick(rng, ((rng.randint(15, 17), 18), (rng.randint(18, 21), 44), (rng.randint(22, 25), 27), (rng.randint(26, 30), 10), (rng.randint(31, 34), 1)))
    return today - timedelta(days=age * 365 + rng.randint(0, 364)), age


def goal_for(rng, age):
    if age < 18:
        return pick(rng, (("Defence", 50), ("NEET UG", 30), ("Other", 20)))
    if age <= 21:
        return pick(rng, (("Defence", 38), ("NEET UG", 27), ("UPSC / Civil Services", 10), ("Other", 25)))
    if age <= 25:
        return pick(rng, (("Defence", 12), ("UPSC / Civil Services", 38), ("NEET PG", 12), ("Other", 38)))
    return pick(rng, (("UPSC / Civil Services", 45), ("NEET PG", 25), ("Other", 30)))


def defence_entry_for(rng, age):
    if age <= 19:
        return pick(rng, (("NDA", 55), ("TES", 25), ("Agniveer", 20)))
    if age <= 24:
        return pick(rng, (("CDS", 30), ("AFCAT", 20), ("Agniveer", 30), ("Territorial Army / JKLI", 20)))
    return pick(rng, (("CDS", 50), ("Territorial Army / JKLI", 50)))


def target_exam_for(rng, goal):
    if goal == "UPSC / Civil Services":
        return pick(rng, (("UPSC Civil Services", 40), ("JKPSC (JKAS)", 25), ("JKSSB", 20), ("JK Police", 10), ("SSC", 5))), ""
    if goal == "Other":
        exam = pick(rng, (("JEE", 15), ("Banking", 15), ("Teaching", 15), ("Nursing / Paramedical", 12), ("Skill / Vocational", 20), ("JKSSB", 13), ("Other", 10)))
        return exam, rng.choice(("Hotel management", "Journalism", "Fashion design", "Photography")) if exam == "Other" else ""
    return "", ""


def qualification_for(rng, age, goal):
    if goal == "NEET PG":
        return "Bachelor's Degree"
    if age < 18:
        return "Class 10"
    if age <= 21:
        return pick(rng, (("Class 12", 60), ("Diploma", 15), ("Bachelor's Degree", 25)))
    if age <= 25:
        return pick(rng, (("Bachelor's Degree", 65), ("Postgraduate", 15), ("Diploma", 10), ("Class 12", 10)))
    return pick(rng, (("Bachelor's Degree", 50), ("Postgraduate", 40), ("Diploma", 10)))


def institution_for(rng, qualification, goal):
    if goal == "NEET PG":
        return pick(rng, (("Government Medical College Srinagar", 60), ("SKIMS Medical College", 40)))
    if qualification == "Class 10":
        return pick(rng, (("Government Higher Secondary School Kupwara", 40), ("Government Higher Secondary School Trehgam", 25), ("Jawahar Navodaya Vidyalaya Kupwara", 20), ("Army Goodwill School", 15)))
    if qualification == "Diploma":
        return "Government Polytechnic Kupwara"
    return pick(rng, (("Government Degree College Kupwara", 40), ("Government Degree College Handwara", 30), ("University of Kashmir", 20), ("IGNOU (distance)", 10)))


def purpose_for(rng, goal):
    if goal == "Other":
        return pick(rng, (("Career Guidance", 38), ("Skill Development", 28), ("Self Study", 26), ("Other", 8)))
    return pick(rng, (("Competitive Exam Preparation", 58), ("Self Study", 30), ("Career Guidance", 12)))


REQUIREMENT_WEIGHTS = {
    "Defence": (("Mock Tests", 60), ("Study Space", 45), ("Books / Study Material", 45), ("Exam Information", 40), ("Mentorship", 25), ("Career Guidance", 15), ("Counselling", 6)),
    "NEET UG": (("Books / Study Material", 65), ("Study Space", 60), ("Mock Tests", 50), ("Internet", 30), ("Mentorship", 15), ("Counselling", 10)),
    "NEET PG": (("Study Space", 70), ("Internet", 45), ("Books / Study Material", 40), ("Mock Tests", 35), ("Computer Access", 20)),
    "UPSC / Civil Services": (("Study Space", 65), ("Books / Study Material", 60), ("Internet", 40), ("Computer Access", 30), ("Mentorship", 30), ("Mock Tests", 25), ("Exam Information", 15)),
    "Other": (("Career Guidance", 55), ("Computer Access", 45), ("Skill Training", 40), ("Internet", 35), ("Counselling", 20), ("Study Space", 20)),
}


def requirements_for(rng, goal):
    options = REQUIREMENT_WEIGHTS[goal]
    wanted = rng.choice((1, 2, 2, 3, 3, 4))
    chosen = []
    while len(chosen) < wanted:
        item = pick(rng, options)
        if item not in chosen:
            chosen.append(item)
    return chosen


def registration_date_for(rng, today):
    # Registrations grew over two years: recent months are busier. The
    # centre is closed on Sundays, so nobody enrolls then.
    month_back = pick(rng, [(m, 26 - m * 0.7) for m in range(26)])
    day = today - timedelta(days=month_back * 30 + rng.randint(0, 29))
    return day - timedelta(days=1) if day.weekday() == 6 else day


def enrolled_at(number):
    return arrival_time(random.Random(f"enrolled-{number}"))


def engagement_for(rng, registered_days_ago):
    """How a student's attendance went after the day they enrolled.

    "once" students came only to enroll (students always enroll in person).
    """
    if registered_days_ago < 30:
        return pick(rng, (("active", 70), ("once", 30)))
    if registered_days_ago < 60:
        return pick(rng, (("active", 38), ("dormant", 45), ("once", 17)))
    if registered_days_ago <= 180:
        return pick(rng, (("active", 20), ("dormant", 12), ("inactive", 55), ("once", 13)))
    return pick(rng, (("active", 10), ("dormant", 7), ("inactive", 73), ("once", 10)))


DAY_FACTOR = {0: 1.0, 1: 1.0, 2: 1.0, 3: 0.95, 4: 0.75, 5: 0.85, 6: 0.0}  # the centre is closed on Sundays


def _keep_stream_stable(rng):
    """Earlier versions drew a preparation stage and exam year here. Drawing
    the same random numbers keeps every later value (and so the demo's
    named students and their visits) unchanged."""
    if rng.random() >= 0.22:
        rng.random()  # the stage pick
    if rng.random() < 0.8:
        rng.random()  # the exam-year pick


def arrival_time(rng):
    slot = pick(rng, (("morning", 62), ("afternoon", 30), ("any", 8)))
    if slot == "morning":
        minutes = int(rng.gauss(10 * 60 + 5, 45))
        if not 9 * 60 <= minutes <= 12 * 60 + 30:  # doors open at 9; no pile-up at the edges
            minutes = rng.randint(9 * 60, 11 * 60)
    elif slot == "afternoon":
        minutes = int(rng.gauss(14 * 60 + 30, 50))
        if not 13 * 60 <= minutes <= 17 * 60 + 30:
            minutes = rng.randint(13 * 60 + 30, 16 * 60)
    else:
        minutes = rng.randint(9 * 60, 17 * 60 + 30)
    return time(minutes // 60, minutes % 60)


CLOSING = time(18, 0)


def departure(number, day, arrived):
    """When a student left: morning arrivals stay about three and a half
    hours, afternoon ones about two, nobody past closing. About 1 in 14
    visits has no check-out, as happens at a real desk."""
    rng = random.Random(f"leave-{number}-{day.isoformat()}")
    if rng.random() < 0.07:
        return None
    morning = arrived.hour < 13
    minutes = max(35, int(rng.gauss(215 if morning else 120, 55 if morning else 35)))
    start = datetime.combine(day, arrived)
    leave = min(start + timedelta(minutes=minutes), datetime.combine(day, CLOSING) - timedelta(minutes=rng.randint(0, 20)))
    if leave <= start:
        leave = start + timedelta(minutes=30)
    return leave.time().replace(second=0)


def active_rate(number):
    return pick(random.Random(f"plan-{number}"), ((0.8, 20), (0.35, 35), (0.12, 45)))


def visits_between(number, start, end, rate):
    visits = {}
    day = start
    while day <= end:
        day_rng = random.Random(f"visit-{number}-{day.isoformat()}")
        if day_rng.random() < rate * DAY_FACTOR[day.weekday()]:
            visits[day] = arrival_time(day_rng)
        day += timedelta(days=1)
    return visits


def visit_plan(number, status, registered, today):
    """Dates (and arrival times) this student visited, up to today. The first
    is always the day they enrolled, in person."""
    rng = random.Random(f"plan-{number}")
    enrolled = (registered, enrolled_at(number))
    if status == "once":
        return [enrolled]
    if status == "active":
        rate = pick(rng, ((0.8, 20), (0.35, 35), (0.12, 45)))
        start, end = max(registered, today - timedelta(days=150)), today
        guarantee = today - timedelta(days=rng.randint(0, 20))
    else:
        age = (today - registered).days
        gap = rng.randint(31, max(31, min(58, age))) if status == "dormant" else rng.randint(61, max(61, age))
        end = today - timedelta(days=gap)
        start = max(registered, end - timedelta(days=rng.randint(5, 60)))
        rate = pick(rng, ((0.45, 30), (0.2, 70)))
        guarantee = end
    visits = visits_between(number, start, end, rate)
    if guarantee.weekday() == 6:
        guarantee -= timedelta(days=1)
    guarantee = max(guarantee, registered)
    visits.setdefault(guarantee, arrival_time(random.Random(f"visit-{number}-{guarantee.isoformat()}")))
    if status != "active":
        visits = {day: at for day, at in visits.items() if day <= end}
    visits[registered] = enrolled[1]
    return sorted(visits.items())


def call_history(rng, status, goal, last_visit, registered, today):
    """Follow-up calls for a student who stopped coming: sometimes a missed
    call first, then what they said."""
    if status == "active" or (status == "dormant" and rng.random() > 0.45) or rng.random() > 0.62:
        return []
    final = pick(rng, (
        ("Plans to Return", 35), ("Preparing from Home", 20), ("Studying at School / College", 20),
        ("Unable to Contact", 15), ("Employed", 10),
    )) if status == "dormant" else pick(rng, (
        ("Preparing from Home", 22), ("Studying at School / College", 18), ("Preparing at Another Institute", 11),
        ("Plans to Return", 8), ("Employed", 9), ("Unable to Contact", 12), ("Wrong Number", 2),
        ("Joined Armed Forces / Selected", 6 if goal == "Defence" else 1), ("Joined Professional Course", 5),
        ("Moved / Relocated", 4), ("No Longer Interested", 4),
    ))
    since = (last_visit or registered) + timedelta(days=3)
    if since > today:
        return []
    last_call = since + timedelta(days=rng.randint(0, max(0, min(80, (today - since).days))))
    calls = []
    if final not in {"Unable to Contact", "Wrong Number"} and rng.random() < 0.35 and last_call - timedelta(days=8) >= since:
        calls.append((last_call - timedelta(days=rng.randint(5, 8)), "Unable to Contact"))
    calls.append((last_call, final))
    return calls


class Command(BaseCommand):
    help = "Create RM demo students with realistic registrations, goals, visits and follow-up calls."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=960)
        parser.add_argument("--top-up", action="store_true", help="Only add check-ins and check-outs for demo students already loaded; never create students. Does nothing when no demo data is loaded.")
        parser.add_argument("--reset", action="store_true", help="Delete earlier demo students, visits and calls first.")
        parser.add_argument("--remove", action="store_true", help="Delete the demo students, visits and calls, then stop.")

    def _remove_demo(self):
        demo_filter = Q()
        for domain in DEMO_DOMAINS:
            demo_filter |= Q(email__endswith=domain)
        demo = Employee.objects.filter(demo_filter, rm_profile__isnull=False)
        demo_ids = list(demo.values_list("id", flat=True))
        # Students enrolled or imported during a demo: added in the app after
        # the demo data was loaded, so their records come after it (real
        # students are entered after --remove).
        loaded = demo.aggregate(first=Min("id"))["first"]
        added = list(
            Employee.objects.filter(email__endswith=APP_DOMAIN, rm_profile__isnull=False, id__gt=loaded)
            .values_list("id", flat=True)
        ) if loaded else []
        students, visits = delete_students(demo_ids + added)
        self.stdout.write(
            f"Removed {len(demo_ids)} demo students, {len(added)} student{'s' if len(added) != 1 else ''} added during demos, "
            f"and {visits} visits."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["remove"]:
            self._remove_demo()
            return
        if options["reset"]:
            self._remove_demo()
        count = options["count"]
        today = timezone.localdate()
        now = timezone.localtime().replace(tzinfo=None)
        existing = {student.email: student for student in Employee.objects.filter(email__endswith="@rm.demo", is_active=True)}
        weekdays = {day.day: day for day in EmployeeShiftDay.objects.all()}
        self.weekday = lambda day: weekdays.get(WEEKDAYS[day.weekday()])
        self.today, self.now = today, now
        if options["top_up"] and not existing:
            self.stdout.write("No demo data is loaded, so there's nothing to top up.")
            return
        attendance = self._top_up(existing, today, now) if existing else []
        left = self._check_out_departed(existing, today, now) if existing else 0
        if options["top_up"]:
            before = Attendance.objects.filter(employee_id__email__endswith="@rm.demo").count()
            Attendance.objects.bulk_create(attendance, batch_size=500, ignore_conflicts=True)
            added = Attendance.objects.filter(employee_id__email__endswith="@rm.demo").count() - before
            self.stdout.write(self.style.SUCCESS(f"Demo data topped up: {added} new check-ins, {left} check-outs."))
            return

        people, created, previous = {}, [], None
        for number in range(1, count + 1):
            email = f"rm-{number:04d}@rm.demo"
            if email in existing:
                continue
            rng = random.Random(f"student-{number}")
            dob, age = age_band_dob(rng, today)
            goal = goal_for(rng, age)
            female = rng.random() < {"Defence": 0.22, "NEET UG": 0.6, "NEET PG": 0.55, "UPSC / Civil Services": 0.4, "Other": 0.45}[goal]
            first = rng.choice(FEMALE if female else MALE)
            last = rng.choice(SURNAMES)
            tehsil, _, villages = pick(rng, [((name, weight, villages), weight) for name, weight, villages in TEHSILS])
            qualification = qualification_for(rng, age, goal)
            fields = {
                "employee_first_name": first, "employee_last_name": last, "badge_id": f"RM-{number:04d}",
                "phone": f"9{rng.randint(419000000, 419999999)}", "gender": "female" if female else "male",
                "dob": dob, "qualification": qualification, "address": f"{rng.choice(villages)}, {tehsil}", "is_active": True,
            }
            if number % 97 == 0 and previous:
                # Siblings: same family phone, surname and village.
                fields.update(phone=previous["phone"], employee_last_name=previous["employee_last_name"], address=previous["address"])
            previous = fields
            people[email] = (number, rng, age, goal, qualification, tehsil, fields)
            created.append(Employee(email=email, **fields))
        Employee.objects.bulk_create(created, batch_size=200)

        students = {student.email: student for student in Employee.objects.filter(email__in=list(people))}
        profiles, plans, status_totals = [], [], {"active": 0, "dormant": 0, "inactive": 0, "once": 0}
        for email, (number, rng, age, goal, qualification, tehsil, fields) in people.items():
            student = students[email]
            registered = registration_date_for(rng, today)
            if registered == today and enrolled_at(number) > now.time():
                # Hasn't walked in yet today: enrolled on the last open day.
                registered -= timedelta(days=2 if today.weekday() == 0 else 1)
            status = engagement_for(rng, (today - registered).days)
            status_totals[status] += 1
            exam, detail = target_exam_for(rng, goal)
            defence = defence_entry_for(rng, age) if goal == "Defence" else ""
            _keep_stream_stable(rng)
            profile = StudentProfile(
                employee=student, career_goal=goal, locality=tehsil, defence_entry=defence,
                target_exam=exam, goal_detail=detail,
                purpose_of_rm=purpose_for(rng, goal), requirements=requirements_for(rng, goal),
                expectations=rng.choice(EXPECTATIONS), registration_date=registered,
                institution=institution_for(rng, qualification, goal),
                guardian_name=f"{rng.choice(MALE)} {fields['employee_last_name']}", guardian_phone=f"9{rng.randint(596000000, 596999999)}",
            )
            profile.purpose_other = "Wants a safe place to spend the day productively." if profile.purpose_of_rm == "Other" else ""
            visits = visit_plan(number, status, registered, today)
            last_visit = visits[-1][0] if visits else None
            calls = call_history(rng, status, goal, last_visit, registered, today)
            returned = False
            if calls and calls[-1][1] == "Plans to Return" and rng.random() < 0.55:
                # Some students who promise to come back do: the call worked.
                back = calls[-1][0] + timedelta(days=rng.randint(2, 9))
                if back.weekday() == 6:
                    back += timedelta(days=1)
                if back <= today:
                    extra = visits_between(number, back, today, 0.3)
                    extra.setdefault(back, arrival_time(random.Random(f"visit-{number}-{back.isoformat()}")))
                    visits = sorted({**dict(visits), **extra}.items())
                    returned = True
            for day, arrived in visits:
                if day == today and arrived > now.time() and day != registered:
                    continue  # not arrived yet
                attendance.append(self._visit(student, day, arrived, ENROLLMENT_VISIT if day == registered else REGULAR_VISIT))
            if calls and returned:
                profile.last_followup_date = calls[-1][0]  # called, then came back
            if calls and not returned:
                called_on, result = calls[-1]
                profile.current_status, profile.last_followup_date = result, called_on
                profile.inactivity_reason = REASONS.get(result, "")
                profile.followup_notes = NOTES.get(result, "Called the student.")
                if result in CALL_BACK_AFTER_DAYS:
                    profile.next_call_date = called_on + timedelta(days=CALL_BACK_AFTER_DAYS[result])
                if result in STATUS_OUTCOMES:
                    profile.outcome, profile.outcome_date = STATUS_OUTCOMES[result], called_on
            profiles.append(profile)
            plans.append((profile, calls))
        StudentProfile.objects.bulk_create(profiles, batch_size=200)
        saved = {profile.employee_id: profile for profile in StudentProfile.objects.filter(employee__email__in=list(people))}
        followups = []
        for profile, calls in plans:
            for called_on, result in calls:
                followups.append(StudentFollowUp(
                    student=saved[profile.employee_id], called_on=called_on, result=result, reason=REASONS.get(result, ""),
                    notes=NOTES.get(result, "Called the student."),
                    next_call_date=called_on + timedelta(days=CALL_BACK_AFTER_DAYS[result]) if result in CALL_BACK_AFTER_DAYS else None,
                ))
        StudentFollowUp.objects.bulk_create(followups, batch_size=500)
        before = Attendance.objects.filter(employee_id__email__endswith="@rm.demo").count()
        Attendance.objects.bulk_create(attendance, batch_size=500, ignore_conflicts=True)
        after = Attendance.objects.filter(employee_id__email__endswith="@rm.demo").count()
        self.stdout.write(self.style.SUCCESS(
            f"RM demo data ready: {len(created)} new students (planned {status_totals}), {len(followups)} calls, "
            f"{after - before} new visits ({after} demo visits in total)."
        ))

    def _visit(self, student, day, arrived, note):
        number = int(student.email[3:7])
        planned = departure(number, day, arrived) if arrived else None
        left = planned
        if left and day == self.today and left > self.now.time():
            left = None  # still in the centre: the check-out is pending (see _check_out_departed)
        minutes = int((datetime.combine(day, left) - datetime.combine(day, arrived)).total_seconds() // 60) if left else 0
        return Attendance(
            employee_id=student, attendance_date=day, attendance_clock_in_date=day, attendance_clock_in=arrived,
            attendance_clock_out=left, attendance_clock_out_date=day if planned else None,
            attendance_worked_hour=f"{minutes // 60:02d}:{minutes % 60:02d}", minimum_hour="00:00", request_description=note,
            attendance_day=self.weekday(day),
        )

    def _check_out_departed(self, existing, today, now):
        """Give demo visits the check-out the seed left pending once the
        student's leaving time has passed.

        A pending check-out is a check-out date without a time. Checking a
        student out, back in or correcting the times at the desk clears that
        mark, so nothing the administrator changed is overwritten. Data loaded
        before check-outs existed (no demo visit has one) gets them all once.
        """
        open_visits = Attendance.objects.filter(
            employee_id__in=existing.values(), attendance_clock_in__isnull=False, attendance_clock_out__isnull=True,
        ).select_related("employee_id")
        demo_visits = Attendance.objects.filter(employee_id__in=existing.values())
        if demo_visits.filter(attendance_clock_out__isnull=False).exists():
            open_visits = open_visits.filter(attendance_clock_out_date__isnull=False)
        changed = []
        for visit in open_visits:
            left = departure(int(visit.employee_id.email[3:7]), visit.attendance_date, visit.attendance_clock_in)
            if not left:
                continue
            if visit.attendance_date == today and left > now.time():
                if not visit.attendance_clock_out_date:  # data from before check-outs: mark it pending
                    visit.attendance_clock_out_date = visit.attendance_date
                    changed.append(visit)
                continue
            minutes = int((datetime.combine(visit.attendance_date, left) - datetime.combine(visit.attendance_date, visit.attendance_clock_in)).total_seconds() // 60)
            visit.attendance_clock_out, visit.attendance_clock_out_date = left, visit.attendance_date
            visit.attendance_worked_hour = f"{minutes // 60:02d}:{minutes % 60:02d}"
            changed.append(visit)
        Attendance.objects.bulk_update(changed, ["attendance_clock_out", "attendance_clock_out_date", "attendance_worked_hour"], batch_size=500)
        return sum(1 for visit in changed if visit.attendance_clock_out)

    def _top_up(self, existing, today, now):
        """Keep students who are still coming coming, up to the current time.

        Only arrivals since the last seed or top-up are added, so a visit the
        administrator removed isn't put back. Students who only came to
        enroll stay that way (the demo's "didn't come back" numbers shouldn't
        drift), and a missing enrollment visit is put back.
        """
        students = list(existing.values())
        # The seed's own visits have no creator (the desk and imports record the administrator).
        last_run = Attendance.objects.filter(employee_id__in=students, created_by__isnull=True).aggregate(last=Max("created_at"))["last"]
        last_run = timezone.localtime(last_run).replace(tzinfo=None) if last_run else None
        last_visits = dict(
            Attendance.objects.filter(employee_id__in=students).order_by().values("employee_id")
            .annotate(last=Max("attendance_date")).values_list("employee_id", "last")
        )
        registered = dict(StudentProfile.objects.filter(employee__in=students).values_list("employee_id", "registration_date"))
        enrolled = set(Attendance.objects.filter(employee_id__in=students, request_description=ENROLLMENT_VISIT).values_list("employee_id", flat=True))
        visits = []
        for email, student in existing.items():
            number = int(email[3:7])
            enrolled_on = registered.get(student.id)
            if enrolled_on and enrolled_on <= today and student.id not in enrolled:
                visits.append(self._visit(student, enrolled_on, enrolled_at(number), ENROLLMENT_VISIT))
            last = last_visits.get(student.id)
            if not last or (today - last).days >= 30 or last >= today or (enrolled_on and last <= enrolled_on):
                continue
            for day, arrived in sorted(visits_between(number, last + timedelta(days=1), today, active_rate(number)).items()):
                if day == today and arrived > now.time():
                    continue
                if last_run and datetime.combine(day, arrived) <= last_run:
                    continue  # an earlier run already added it (or chose not to)
                visits.append(self._visit(student, day, arrived, REGULAR_VISIT))
        return visits
