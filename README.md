# Roshan Mustaqbil

## Student attendance, follow-up and career-goal tracking

Roshan Mustaqbil is a small administration system for a youth centre in
Kupwara. The centre's administrator uses it to check students in and out each
day, enroll students, call students who have stopped coming, and understand
who uses the centre and why. There is one sign-in, the administrator, who does
everything.

Students enroll in person at the centre (there is no online sign-up), so the
day a student enrolls is recorded as their first visit.

## What it does

- **Check-in and check-out**: search by registration number, phone or name.
  Enter on a registration or phone number checks that student in; Enter
  again when they leave checks them out, and again if they come back (still
  one visit for the day). A second Enter within five minutes changes
  nothing, and a number shared by siblings lists everyone on it instead.
  "Who's here" shows who is in the centre now and who has left, with a
  **Check out** button on each and **Check everyone out…** for closing time.
  Undo, correct a visit's times, remove a visit, a "regulars not in yet"
  list, and back-dated entry from a paper register (up to 30 days). A
  forgotten check-out never loses the visit; it's only left out of the
  time-in-the-centre numbers.
- **Dashboard**: how many current students came in the last 30 days, the trend
  over six months, today so far (and how many are in the centre now) against
  a typical day, the typical time in the centre and how stays spread, today
  hour by hour, who is waiting for a call, and what happened to students who
  stopped coming.
- **Follow-up calls**: four call lists, easiest to win back first: new
  students who didn't come back (enrolled 7–60 days ago), regulars who
  missed this week, slipping away, and inactive. Tap-to-call numbers and
  "Save & next". Every call is kept in a history; students who couldn't be
  reached come back to the list after a week. Students who were selected,
  joined a course, moved away or lost interest "move on" instead of counting
  as inactive for ever. "Waiting for a call" is the same number on the
  dashboard, the call list and the downloaded call sheet.
- **Students**: search, filter (status, goal, exam, area,
  support needed, age, gender, qualification, enrollment date, follow-up),
  sort, page through and download as CSV. Profiles show a 12-month visit
  calendar, each visit's check-in and check-out times, the student's typical
  stay and the call history.
- **Enrollment**: a sectioned form with duplicate warnings, 10-digit phone
  checks, date of birth or approximate age, area, career goal and the exam
  or Defence entry scheme. Enrolling marks the student present on the enrollment
  date; that visit can't be deleted on its own, and correcting the date moves
  it. A student enrolled by mistake can be removed. Students never get a
  login.
- **Attendance dashboard, career goals and analytics**: busiest days and
  arrival times, how many are in the centre hour by hour, how long students
  stay, how often and how long each goal group comes, Defence entry schemes and other
  exams, enrollments and whether
  students came back, how long they keep coming before they stop, age,
  gender, area, needs (compared with students who stopped) and expectations.
- **Import**: bring existing registers and past attendance (with check-in
  and check-out times, if the register has them) in from a CSV file, with a
  row-by-row check before anything is saved. Each imported
  student is recorded as present on their enrollment date; visits dated
  before a student enrolled are flagged.
- **Look and feel**: every screen sits on one backdrop, the Kupwara hills in
  the morning, with frosted-glass panels over it, and a night version. The
  glass turns solid for people who ask their system for less transparency.

## How a student's progress is tracked

Three things, each with a clear source, so nobody has to keep a progress
score up to date:

1. **Attendance** (automatic, from the desk). Every visit is recorded,
   starting with the day they enrolled, with check-in and check-out times,
   so the centre also sees how long students stay. From the last visit
   (not the length of stay) each student is
   **Active** (came in the last 30 days), **Slipping away** (30–59 days) or
   **Inactive** (60+ days), and "didn't come back after enrolling" picks out
   those who came only once. The profile shows a 12-month visit calendar.
2. **Their goal** (entered once, at enrollment): the career goal and the exam
   or Defence entry scheme they're aiming for. **Career goals** shows how
   many students each goal has and how regularly each group comes.
3. **Follow-up calls** (entered by whoever makes the call): what a student who
   stopped is doing now (studying, preparing at home, employed and so on),
   and outcomes that mean they have **moved on**: selected, joined a
   professional course, moved away or no longer interested.

Nobody has to fill in or update a progress score.

## Install on a new machine (one command)

### Windows PC

In **Command Prompt** (Git for Windows installed):

```bat
git clone https://github.com/jatin4614/roshan-mustaqbil-demo.git C:\RoshanMustaqbil && C:\RoshanMustaqbil\setup.bat
```

Without git, use **Code > Download ZIP** on GitHub, unzip it somewhere
permanent (such as `C:\RoshanMustaqbil`) and double-click **`setup.bat`** in
it. Setup needs the internet the first time and takes 10 to 20 minutes. It:

- installs Python 3.12 if no Python 3.12 to 3.14 is found (through winget);
- installs the app's packages into `.venv`;
- writes the settings file `.env` with a new secret key, and creates the
  database `roshan_mustaqbil.sqlite3`;
- asks you to choose the administrator's password (sign in as `admin`);
- asks whether to load the demo data (choose **No** for real use);
- puts a **Roshan Mustaqbil** shortcut on the desktop.

Then double-click **Roshan Mustaqbil** on the desktop whenever the centre
opens. It starts the app in a window called "Roshan Mustaqbil app - keep
open" (keep it open) and opens http://127.0.0.1:8001. The first time,
Windows may ask whether Python can use the network: allow **Private
networks** so other devices in the building can connect, at
`http://<this PC's name>:8001` or `http://<its address>:8001`.

Unattended, with nothing asked:

```bat
setup.bat -Quiet -AdminPassword "choose-a-password" -Demo no
```

(`-Demo yes` loads the 960 demo students, `-NoShortcut` skips the desktop
shortcut and `-Start` starts the app at the end.)

### Linux or macOS

```bash
git clone https://github.com/jatin4614/roshan-mustaqbil-demo.git roshan-mustaqbil && cd roshan-mustaqbil && ./setup.sh
```

It does the same as `setup.bat` (except the desktop shortcut). If no Python
3.12 to 3.14 with its development headers is found, it fetches Python 3.12
with [uv](https://docs.astral.sh/uv/), without admin rights. Unattended:
`./setup.sh --quiet --admin-password "choose-a-password" --demo no`. Start
the app with `scripts/start.sh` (Ctrl+C stops it).

### Updating and re-running

Running setup again is safe: it keeps the settings, database and
administrator's password, and brings the packages and database up to date.
To update, `git pull` (or unzip the new version over the old one, keeping
`.env` and `roshan_mustaqbil.sqlite3`) and run setup again. To change the
password: `.venv\Scripts\python manage.py changepassword admin` (on Linux or
macOS, `.venv/bin/python`). Back up `roshan_mustaqbil.sqlite3`: it holds all
the centre's data.

To share the app beyond the building, install Microsoft's dev tunnel tool
(`winget install Microsoft.devtunnel`), create a tunnel once
(`docs/DEPLOYMENT_OPTIONS.md`, section 1, "A link that stays the same"), and
start the app with `scripts\start.bat <tunnel-id>`, or set `RM_TUNNEL_ID`.
The installed app runs in its simple local mode, which shows technical
details on error pages; for a link used every day, host it instead
(`docs/DEPLOYMENT_OPTIONS.md`).

### By hand

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py bootstrap_roshan_mustaqbil_demo --password "choose-a-password"
.venv\Scripts\python manage.py seed_youth_centre_demo
.venv\Scripts\python manage.py runserver 127.0.0.1:8001
```

(On Linux or macOS use `.venv/bin/` instead of `.venv\Scripts\`; skip the
`seed_youth_centre_demo` line for real use.)

## The demo data

`docs/DEMO_SCRIPT.md` walks through a 22-minute demo.

The seed creates 960 students from Kupwara with realistic enrollments, goals,
visits with check-in and check-out times, and follow-up calls (the centre is
closed on Sundays; most students arrive in the morning and stay two to four
hours; a few check-outs are deliberately missing, as in real life). The first
run is always the same, so the demo script's examples match. The desktop
shortcut (`scripts\start.bat`) adds the day's check-ins and check-outs so far
(`seed_youth_centre_demo --top-up`, which does nothing without demo data); it
never rewrites records you have changed. `--reset` replaces the demo data
(and removes students enrolled or imported during a demo); `--remove` deletes
it all before real students are entered.

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
enrollment visit on their enrollment date, every check-out is after its
check-in, "didn't come back after enrolling" gives the same students
everywhere, no student is in two call queues, phone numbers are valid, and
removed wording hasn't returned. The desktop shortcut runs it each time the
app starts. It exits with an
error if a check fails.

## Technology

Django, with SQLite on a single PC or PostgreSQL and Gunicorn when hosted,
built on the Horilla HRMS foundations. The
centre screens live in `base/rm*.py`, `templates/rm/` and `static/rm/`.

## License

See [LICENSE](LICENSE).
