# Roshan Mustaqbil

## Student Attendance & Career Goal Tracking

Roshan Mustaqbil is a simple administration system for a youth-development
centre. It helps centre staff enrol students, record daily attendance, track
career preparation, and review centre-wide analytics from one dashboard.

## Demo Features

- **Dashboard** — student totals, today's attendance, goal distribution, and
  students needing attention.
- **Students** — enrol and maintain student profiles, contact details,
  education, guardian details, and career preparation information.
- **Attendance** — mark all students present, change individual statuses, and
  review attendance history.
- **Goals** — track Defence, UPSC / Civil Services, NEET UG, and NEET PG
  preparation, progress percentage, status, and remarks.
- **Analytics** — attendance and career-goal trends for the whole centre.

## Local Demo

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

Open `http://127.0.0.1:8001` and sign in with:

```text
Username: admin
Password: Admin123
```

The seed command creates 15 demo students with varied attendance levels,
career goals, progress states, and attendance records.

## Render Deployment

The repository includes `render.yaml` for a Render web service and managed
PostgreSQL database. Follow `RENDER_DEPLOYMENT.md` after connecting the
repository in Render.

For a free Render service, configure these environment variables:

```text
RENDER_ASYNC_RELEASE_TASKS=1
GUNICORN_WORKERS=1
GUNICORN_THREADS=1
```

## Technology

The application uses Django, PostgreSQL, Gunicorn, and the existing component
and attendance foundations retained for a stable demo experience.

## License

See [LICENSE](LICENSE).
