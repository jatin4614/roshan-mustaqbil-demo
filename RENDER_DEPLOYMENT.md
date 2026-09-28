# Render demo deployment

This repository includes `render.yaml` for a fresh Roshan Mustaqbil demo:

1. Create a new GitHub repository and push this branch to it. Do not commit `.env`, `media/`, `TestDB.sqlite3`, or `.venv`.
2. In Render, select **New +** > **Blueprint**, connect the GitHub repository, and select `render.yaml`.
3. Set `DEMO_ADMIN_PASSWORD` to the password you want for the administrator (for the requested demo, use `Admin123`).
4. Create the Blueprint and wait for the web service and PostgreSQL database to become available.
5. Open the generated `onrender.com` URL and sign in as `admin` with the chosen password.

The first deployment opens a temporary setup listener while database migrations run, which keeps a free Render web service alive during initialization. The one-time deployment hook then creates the Roshan Mustaqbil administrator and seeds the 15-student demo dataset. Subsequent deploys retain the database and do not reset administrator credentials or student updates.

Render free services can sleep after inactivity and may take a short time to wake up. Use a paid Render web-service plan for a no-sleep senior-demo link.
