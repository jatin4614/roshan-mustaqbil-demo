# Roshan Mustaqbil

## Student attendance, follow-up and career-goal tracking

Roshan Mustaqbil is a small administration system for a youth centre in
Kupwara. The centre's administrator uses it to mark daily attendance, enroll
students, call students who have stopped coming, and understand who uses the
centre and why. There is one sign-in, the administrator, who does
everything.

Students enroll in person at the centre (there is no online sign-up), so the
day a student enrolls is recorded as their first visit.

## What it does

- **Mark attendance**: search by registration number, phone or name. Enter
  on a registration or phone number marks that student present; a number
  shared by siblings lists everyone on it instead. Undo, remove from today's
  list, a "regulars not in yet" list, and back-dated entry from a paper
  register (up to 30 days).
- **Dashboard**: how many current students came in the last 30 days, the trend
  over six months, today so far against a typical day, who is waiting for a
  call, and what happened to students who stopped coming.
- **Follow-up calls**: four call lists, easiest to win back first: new
  students who didn't come back (enrolled 7–60 days ago), regulars who
  missed this week, slipping away, and inactive. Tap-to-call numbers and
  "Save & next". Every call is kept in a history; students who couldn't be
  reached come back to the list after a week. Students who were selected,
  joined a course, moved away or lost interest "move on" instead of counting
  as inactive for ever. "Waiting for a call" is the same number on the
  dashboard, the call list and the downloaded call sheet.
- **Students**: search, filter (status, goal, exam, preparation stage, area,
  support needed, age, gender, qualification, enrollment date, follow-up),
  sort, page through and download as CSV. Profiles show a 12-month visit
  calendar and the call history.
- **Enrollment**: a sectioned form with duplicate warnings, 10-digit phone
  checks, date of birth or approximate age, area, target exam, preparation
  stage and exam year. Enrolling marks the student present on the enrollment
  date; that visit can't be deleted on its own, and correcting the date moves
  it. A student enrolled by mistake can be removed. Students never get a
  login.
- **Attendance dashboard, career goals and analytics**: busiest days and
  hours, how often each goal group comes, Defence entry schemes and other
  exams, preparation stages, exams coming up, enrollments and whether
  students came back, how long they keep coming before they stop, age,
  gender, area, needs (compared with students who stopped) and expectations.
- **Import**: bring existing registers and past attendance in from a CSV
  file, with a row-by-row check before anything is saved. Each imported
  student is recorded as present on their enrollment date; visits dated
  before a student enrolled are flagged.
- **Look and feel**: every screen sits on one backdrop, the Kupwara hills in
  the morning, with frosted-glass panels over it, and a night version. The
  glass turns solid for people who ask their system for less transparency.

## How a student's progress is tracked

Progress is tracked in three layers, from what the centre sees every day to
how things turn out:

1. **Coming to the centre** (automatic, from attendance). Every visit is
   recorded, starting with the day they enrolled. From the last visit each
   student is **Active** (came in the last 30 days), **Slipping away** (30–59
   days) or **Inactive** (60+ days), and "didn't come back after enrolling"
   picks out those who came only once. The profile shows a 12-month visit
   calendar.
2. **Preparing for their goal** (recorded at enrollment, updated on their
   details): career goal, the exam or Defence entry scheme, the preparation
   stage (just starting, building basics, regular practice and mock tests,
   appeared before, awaiting result) and the exam year. **Career goals**
   shows where each group stands.
3. **How it turned out** (recorded from follow-up calls): what a student who
   stopped is doing now (studying, preparing at home, employed and so on),
   and outcomes that mean they have **moved on**: selected, joined a
   professional course, moved away or no longer interested.

The preparation stage keeps only its latest value, so the app shows where
each student is now rather than how their stage changed over time.

## Local demo

```bash
git clone https://github.com/jatin4614/roshan-mustaqbil-demo.git
cd roshan-mustaqbil-demo
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py bootstrap_roshan_mustaqbil_demo --password Admin123
.venv\Scripts\python manage.py seed_youth_centre_demo
.venv\Scripts\python manage.py runserver 127.0.0.1:8001
```

Open `http://127.0.0.1:8001` and sign in as `admin` with password `Admin123`.
Change it before sharing a link to the app:
`.venv\Scripts\python manage.py changepassword admin`.

`docs/DEMO_SCRIPT.md` walks through a 15-minute demo.

The seed creates 960 students from Kupwara with realistic enrollments, goals,
visits and follow-up calls (the centre is closed on Sundays; most students
arrive in the morning). The first run is always the same, so the demo script's
examples match. Run it again later to add the day's check-ins so far; it never
rewrites records you have changed. `--reset` replaces the demo data (and
removes students enrolled or imported during a demo); `--remove` deletes it
all before real students are entered.

## Putting the demo online

`docs/DEPLOYMENT_OPTIONS.md` compares the ways to share the demo: VS Code port
forwarding from this PC (quickest), tunnels, Codespaces, Render, Railway,
Azure and Fly.io. `render.yaml` defines a Render web service and PostgreSQL
database; see `RENDER_DEPLOYMENT.md`.

## Checking the data

```bash
.venv\Scripts\python manage.py review_rm
```

checks the rules the screens depend on: every student has exactly one
enrollment visit on their enrollment date, "didn't come back after enrolling"
gives the same students everywhere, no student is in two call queues, phone
numbers are valid, and removed wording hasn't returned. It exits with an
error if a check fails.

## Technology

Django, PostgreSQL and Gunicorn, built on the Horilla HRMS foundations. The
centre screens live in `base/rm*.py`, `templates/rm/` and `static/rm/`.

## License

See [LICENSE](LICENSE).
