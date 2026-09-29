# Render deployment

This repository includes `render.yaml` for a Roshan Mustaqbil deployment:

1. Push this branch to a GitHub repository. Do not commit `.env`, `media/`,
   `TestDB.sqlite3` or `.venv`.
2. In Render, select **New +** > **Blueprint**, connect the repository and
   select `render.yaml`.
3. Render asks for `DEMO_ADMIN_PASSWORD`: the password for the `admin`
   account (and, in a demo, the `desk` and `coordinator` accounts). It is not
   stored in the repository.
4. Create the Blueprint and wait for the web service and database.
5. Open the `onrender.com` URL and sign in as `admin`.

The first deployment creates the administrator, the three staff roles and
the demo data (960 students with visits and follow-up calls). Later starts
only add the day's check-ins so far; they never rewrite changes made in the
app.

## Going live with real students

1. Set `RM_SEED_DEMO_DATA` to `0` in the Render dashboard.
2. Remove the demo data: `python manage.py seed_youth_centre_demo --remove`
   (Render shell).
3. Sign in as `admin`, open **Staff accounts** (profile menu) and switch off
   the `desk` and `coordinator` demo accounts. Add real staff with their roles.
4. Import the existing register from **Students > Import from a spreadsheet**.

Free Render services sleep after inactivity and take a while to wake up, and
free databases are time-limited. Use paid plans for day-to-day use at the
centre.
