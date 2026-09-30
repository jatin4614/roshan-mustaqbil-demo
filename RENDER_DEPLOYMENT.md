# Render deployment

This repository includes `render.yaml` for a Roshan Mustaqbil deployment:

1. Push this branch to a GitHub repository. Do not commit `.env`, `media/`,
   `TestDB.sqlite3` or `.venv`.
2. In Render, select **New +** > **Blueprint**, connect the repository and
   select `render.yaml`.
3. Render asks for `DEMO_ADMIN_PASSWORD`: the password for the `admin`
   account, the only sign-in. It is not stored in the repository. The deploy
   stops with an error if it's left blank.
4. Create the Blueprint and wait for the web service and database.
5. Open the `onrender.com` URL and sign in as `admin`.

The first deployment creates the administrator and the demo data (960
students with visits, check-in and check-out times, and follow-up calls).
Later starts only add the day's check-ins and check-outs so far for students
who are still coming; they never rewrite changes made in the app.

## Going live with real students

1. In the Render dashboard, set `RM_SEED_DEMO_DATA` to `0` and
   `RM_REMOVE_DEMO_DATA` to `1`, and deploy. The start-up script removes the
   demo students, and any students added while the demo data was loaded
   (free Render services have no shell, so this replaces running
   `seed_youth_centre_demo --remove` by hand).
2. Set `RM_REMOVE_DEMO_DATA` back to `0`.
3. Sign in as `admin` and change the password (profile menu > Change
   password).
4. Import the existing register from **Students > Import from a spreadsheet**,
   and its past attendance from the **Past attendance** tab.

Free Render services sleep after inactivity and take a while to wake up, and
free databases are time-limited. Use paid plans for day-to-day use at the
centre.
