# Roshan Mustaqbil

## Student attendance, follow-up and career-goal tracking

Roshan Mustaqbil is a small administration system for a youth centre in
Kupwara. Centre staff use it to mark daily attendance, enroll students, call
students who have stopped coming, and understand who uses the centre and why.

## What it does

- **Mark attendance**: search by registration number, phone or name. Enter
  on a registration or phone number marks that student present; a number
  shared by siblings lists everyone on it instead. Undo, remove from today's
  list, a "regulars not in yet" list, and back-dated entry from a paper
  register (up to 30 days).
- **Dashboard**: how many current students came in the last 30 days, the trend
  over six months, today so far against a typical day, who is waiting for a
  call, and what happened to students who stopped coming.
- **Follow-up calls**: a prioritised call list (regulars who missed this week,
  slipping away, inactive, never came) with tap-to-call numbers and "Save &
  next". Every call is kept in a history; students who couldn't be reached
  come back to the list after a week. Students who were selected, joined a
  course, moved away or lost interest "move on" instead of counting as
  inactive for ever.
- **Students**: search, filter (status, goal, exam, preparation stage, area,
  support needed, age, gender, qualification, enrollment date, follow-up),
  sort, page through and download as CSV. Profiles show a 12-month visit
  calendar and the call history.
- **Enrollment**: a sectioned form with duplicate warnings, 10-digit phone
  checks, date of birth or approximate age, area, target exam, preparation
  stage and exam year. Enrolling from the attendance desk marks the student
  present too. Students never get a login.
- **Attendance dashboard, career goals and analytics**: busiest days and
  hours, how often each goal group comes, Defence entry schemes and other
  exams, preparation stages, exams coming up, enrollments and whether they
  came, how long students keep coming before they stop, age, gender, area,
  needs (compared with students who stopped) and expectations.
- **Import**: bring existing registers and past attendance in from a CSV
  file, with a row-by-row check before anything is saved.
- **Staff accounts and roles**: front desk, coordinator and manager.
  Managers add staff and reset passwords; new staff choose their own password
  when they first sign in.

| Role | Can do |
|---|---|
| Front desk | Mark attendance, enroll students, look up a student, attendance history |
| Coordinator | Everything above, plus student lists, follow-up calls, imports, exports, dashboards and analytics |
| Manager | Everything, plus staff accounts |

## Local demo

```bash
git clone https://github.com/jatin4614/roshan-mustaqbil-demo.git
cd roshan-mustaqbil-demo
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py bootstrap_roshan_mustaqbil_demo --password Admin123 --demo-staff
.venv\Scripts\python manage.py seed_youth_centre_demo
.venv\Scripts\python manage.py runserver 127.0.0.1:8001
```

Open `http://127.0.0.1:8001` and sign in:

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin123` | Manager |
| `coordinator` | `Admin123` | Coordinator |
| `desk` | `Admin123` | Front desk |

`docs/DEMO_SCRIPT.md` walks through a 15-minute demo.

The seed creates 960 students from Kupwara with realistic enrollments, goals,
visits and follow-up calls (the centre is closed on Sundays; most students
arrive in the morning). The first run is always the same, so the demo script's
examples match. Run it again later to add the day's check-ins so far; it never
rewrites records staff have changed. `--reset` replaces the demo data;
`--remove` deletes it before real students are entered.

## Render deployment

`render.yaml` defines a Render web service and PostgreSQL database; see
`RENDER_DEPLOYMENT.md`.

## Technology

Django, PostgreSQL and Gunicorn, built on the Horilla HRMS foundations. The
centre screens live in `base/rm*.py`, `templates/rm/` and `static/rm/`.

## License

See [LICENSE](LICENSE).
