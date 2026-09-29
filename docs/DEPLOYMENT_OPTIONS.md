# Putting the demo online

How to give people a link to the Roshan Mustaqbil demo, from "in the next five
minutes, from this PC" to "a hosted link that works for months".

## Which one to use

- **Presenting today, or a link for a few hours:** VS Code port forwarding
  (section 1). It's built into VS Code, needs nothing installed and is already
  set up on this PC. The link works while this PC is on and VS Code is open.
- **A link people can open any time for the next few weeks, free:** Render
  (section 5). `render.yaml` in this repository does the whole setup. It sleeps
  when nobody uses it, so open it a minute before a demo.
- **A steady link for months:** Railway (section 6) at about $5 a month, or a
  paid Render plan. Choose Azure (section 7) if the organisation already uses
  Microsoft Azure or has Azure credits.

## Options at a glance

| | Runs on | First setup | Cost | Link stays up | From VS Code |
|---|---|---|---|---|---|
| 1. VS Code port forwarding | This PC | 2 minutes | Free | While this PC and VS Code are on | Built in: **Ports** panel |
| 2. Cloudflare quick tunnel | This PC | 5 minutes | Free, no account | While the command runs; new link each time | VS Code terminal |
| 3. ngrok | This PC | 10 minutes | Free: one fixed link, 20,000 requests and 1 GB a month | While the command runs | VS Code terminal |
| 4. GitHub Codespaces | GitHub's cloud | 30 minutes | Free: 60 hours a month on a 2-core machine | While the codespace runs; it stops when idle | GitHub Codespaces extension |
| 5. Render | Render's cloud | 20 minutes, mostly waiting | Free, with limits (below) | Always; sleeps after 15 idle minutes | Push from Source Control; Render redeploys |
| 6. Railway | Railway's cloud | 20 minutes | $5 trial credit, then $5 a month | Always | Push from Source Control, or `railway up` in the terminal |
| 7. Azure App Service | Microsoft Azure | 1–2 hours | Paid web app; database free for 12 months on a new account | Always | Azure App Service extension |
| 8. Fly.io | Fly.io's cloud | 45 minutes | No free tier for new accounts; card required | Always | `flyctl` in the terminal |

Options 1–4 run the app with its local settings and the demo database on the
machine they run on. Options 5–8 run the production Docker image with
PostgreSQL and `DEBUG` off.

## Before sharing any link

- **Change the demo password.** `Admin123` is written in the README, and
  `admin` is the only sign-in. Before a public link, run
  `.venv\Scripts\python manage.py changepassword admin`, or on a hosted
  option set your own `DEMO_ADMIN_PASSWORD`.
- **Demo data only.** Don't put real students' names and phone numbers on a
  free tier or a tunnel.
- **Options 1–4 run with `DEBUG` on.** An error page shows technical details.
  That's fine for a presentation; for a link left open for days, use a hosted
  option.
- **Sign-in lockouts.** After 5 wrong passwords, an account is locked for 30
  minutes. Through a tunnel, every visitor appears to come from this PC, so
  one person's mistakes can lock that account for everyone. To unlock:
  `.venv\Scripts\python manage.py axes_reset`.

## What this repository already has

| What | Where |
|---|---|
| Production Docker image (Gunicorn, non-root user, health check) | `Dockerfile`, `docker/gunicorn.conf.py` |
| Start-up script: waits for PostgreSQL, runs migrations, creates the administrator (the only sign-in) and the demo data (when `RM_SEED_DEMO_DATA=1`), removes the demo data when going live (`RM_REMOVE_DEMO_DATA=1`), and collects static files | `docker/entrypoint.sh` |
| Listens on the platform's `$PORT` | `docker/gunicorn.conf.py` |
| Static files served by the app itself (WhiteNoise); no separate web server needed | `horilla/settings/base.py` |
| Database from a single `DATABASE_URL` | `horilla/settings/base.py` |
| Render's hostname trusted automatically | `horilla/settings/base.py` (`RENDER_EXTERNAL_HOSTNAME`) |
| One-click Render setup: web service and PostgreSQL in Singapore | `render.yaml`, `RENDER_DEPLOYMENT.md` |
| Refuses to start in production with a default `SECRET_KEY`, `ALLOWED_HOSTS=*` or a default `DB_INIT_PASSWORD` | `horilla/settings/security.py` |
| Health checks at `/health/` and `/ready/`, not redirected to HTTPS (platforms probe over plain HTTP) | `horilla/urls.py`, `horilla/settings/security.py` |
| Tunnel hostnames allowed in this PC's `.env` (not committed) | `.env` |

**Memory:** one app process uses about 360 MB, measured on this PC after
loading every page type. The HR recruitment module loads a language model at
start-up, which accounts for part of that. It fits in a 512 MB free instance
with one worker (which `render.yaml` sets) but has little room to spare. If a
hosted app restarts with "out of memory", move to a plan with 1 GB or more.

---

## 1. VS Code port forwarding (fastest)

VS Code can forward a port on this PC to a public HTTPS address (Microsoft
dev tunnels). Nothing to install.

1. Start the app, if it isn't running:

   ```bash
   .venv\Scripts\python manage.py runserver 127.0.0.1:8001
   ```

2. In VS Code open the **Ports** panel (next to **Terminal**; or Command
   Palette > **Ports: Focus on Ports View**).
3. **Forward a Port** > `8001`. Sign in with GitHub the first time.
4. Right-click the port > **Port Visibility** > **Public**. A private port can
   only be opened by you, signed in with the same GitHub account.
5. Copy the **Forwarded Address** (something like
   `https://abcd1234-8001.inc1.devtunnels.ms`) and share it.

Visitors may see a one-time dev tunnels notice page; they click **Continue**.
The link stops when you stop forwarding, close VS Code or the PC sleeps.
There are bandwidth limits on tunnels, generous for a demo.

**Already done on this PC:** `.env` allows the tunnel hostnames. Without it,
Django answers "Bad Request (400)" to the new address, and signing in fails
with "CSRF verification failed (403)". On another machine, add these lines to
`.env` and restart the app:

```ini
ALLOWED_HOSTS=localhost,127.0.0.1,.devtunnels.ms,.trycloudflare.com,.ngrok-free.app,.ngrok-free.dev,.app.github.dev
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://localhost:8001,http://127.0.0.1:8001,https://*.devtunnels.ms,https://*.trycloudflare.com,https://*.ngrok-free.app,https://*.ngrok-free.dev,https://*.app.github.dev
```

These also cover options 2–4.

## 2. Cloudflare quick tunnel (no account)

```bash
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://127.0.0.1:8001
```

It prints a link like `https://random-words.trycloudflare.com`. No sign-in
for you or visitors. The link changes every time and has no uptime
guarantee; press Ctrl+C to stop it.

## 3. ngrok (a link that stays the same)

1. Create a free account at ngrok.com, install ngrok and run the
   `ngrok config add-authtoken …` command from its dashboard.
2. The dashboard gives you one free fixed domain. Start the tunnel with the
   command it shows for that domain, pointing at port 8001.

The free plan shows visitors a warning page before the app (once every 7
days per visitor) and allows 20,000 requests and 1 GB a month: enough for a
few demos, not for daily use.

## 4. GitHub Codespaces (runs in GitHub's cloud, not on this PC)

Useful when this PC can't stay on. The repository is public, so any GitHub
account can open it.

1. In VS Code install **GitHub Codespaces**, then Command Palette >
   **Codespaces: Create New Codespace** >
   `jatin4614/roshan-mustaqbil-demo` > branch `main` > 2-core.
2. In the codespace's terminal:

   ```bash
   sudo apt-get update && sudo apt-get install -y libcairo2-dev pkg-config
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   printf 'CSRF_TRUSTED_ORIGINS=https://*.app.github.dev\nTIME_ZONE=Asia/Kolkata\n' > .env
   python manage.py migrate
   python manage.py bootstrap_roshan_mustaqbil_demo --password 'choose-a-password'
   python manage.py seed_youth_centre_demo
   python manage.py runserver 0.0.0.0:8001
   ```

3. **Ports** panel > port 8001 > **Port Visibility** > **Public**. The link
   looks like `https://<codespace-name>-8001.app.github.dev`.

A free GitHub account includes 120 core-hours a month (60 hours on a 2-core
machine). A codespace stops after 30 idle minutes; restart it and run the
last command again. The first `pip install` takes several minutes.

## 5. Render (recommended free hosted link)

`render.yaml` creates the web service and database, runs the migrations and
loads the demo data on the first start. Step by step: `RENDER_DEPLOYMENT.md`.

1. Commit and push `main` to GitHub (VS Code **Source Control** > **Sync**).
2. At dashboard.render.com: **New +** > **Blueprint** > connect GitHub > choose
   `roshan-mustaqbil-demo`.
3. Enter a `DEMO_ADMIN_PASSWORD` when asked. It becomes the password for
   `admin`, the only sign-in. The deploy stops with an error if it's blank.
4. **Apply**. The first build takes 10–20 minutes. Then open the
   `https://roshan-mustaqbil-demo.onrender.com` link (or the one Render shows).

Every later push to `main` redeploys automatically, so you can keep working
in VS Code and push.

Free plan limits:

- The web service sleeps after 15 minutes without visitors; the next visit
  takes about a minute to wake it. Open the link a couple of minutes before a
  demo.
- 750 free instance hours a month: enough for one always-on service.
- The free PostgreSQL database expires 30 days after it's created. Render
  then gives 14 days to upgrade before deleting it. For a longer demo, upgrade
  the database or create the Blueprint again (which reloads the demo data).
- No card needed.

## 6. Railway

1. At railway.com: **New Project** > **Deploy from GitHub repo** >
   `roshan-mustaqbil-demo`. Railway finds the `Dockerfile`.
2. In the project: **+ New** > **Database** > **PostgreSQL**.
3. On the web service > **Variables**, add:

   ```ini
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   DEBUG=False
   HORILLA_ENV=production
   SECRET_KEY=<a long random value>
   DB_INIT_PASSWORD=<another random value>
   ALLOWED_HOSTS=.up.railway.app,healthcheck.railway.app
   CSRF_TRUSTED_ORIGINS=https://*.up.railway.app
   TIME_ZONE=Asia/Kolkata
   RM_SEED_DEMO_DATA=1
   DEMO_ADMIN_USERNAME=admin
   DEMO_ADMIN_PASSWORD=<choose one>
   GUNICORN_WORKERS=1
   GUNICORN_THREADS=4
   ```

   To make a random value:
   `.venv\Scripts\python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

4. **Settings** > **Networking** > **Generate Domain**. Optionally set the
   health check path to `/health/`.

From VS Code instead of the website: in the terminal,
`npm install -g @railway/cli`, then `railway login`, `railway link` and
`railway up` (deploys the folder as it is, without pushing to GitHub).

Cost: new accounts get a one-time $5 trial credit for up to 30 days. After
that, the Hobby plan is $5 a month, which includes $5 of usage; a small demo
like this usually stays within it.

## 7. Azure App Service (the VS Code-native route)

Microsoft's **Azure App Service** extension for VS Code
(`ms-azuretools.vscode-azureappservice`) creates and deploys web apps from the
editor. This PC already has **Container Tools**
(`ms-azuretools.vscode-containers`), which can deploy an image to App Service
too.

The `Dockerfile` installs system libraries (Cairo, Pango and others) for the
PDF and image packages. Azure's built-in Python build may not have them, so
deploy the app as a **container**, the same image Render and Railway run:

1. **Build the image.** Docker isn't installed on this PC. Either install
   Docker Desktop and build `Dockerfile`, or add a GitHub Actions workflow
   that builds it and publishes it to the GitHub Container Registry
   (`ghcr.io/jatin4614/roshan-mustaqbil-demo`).
2. **Database.** Create an **Azure Database for PostgreSQL flexible server**,
   choosing *Burstable B1MS* with 32 GB storage or less. A new Azure free
   account includes 750 hours a month of it for 12 months.
3. **Web app.** In VS Code: Azure panel > App Service > **Create New Web
   App… (Advanced)** > Linux > a **Basic B1** plan or larger > point it at the
   image. The free F1 plan isn't suitable: it allows 60 CPU minutes a day and
   1 GB of storage, and doesn't run custom containers.
4. **Settings.** In the web app's **Environment variables**, add the same
   variables as Railway, with `DATABASE_URL` from step 2 (append
   `?sslmode=require`), `ALLOWED_HOSTS=.azurewebsites.net`,
   `CSRF_TRUSTED_ORIGINS=https://*.azurewebsites.net`,
   `SECURE_SSL_REDIRECT=True` and `WEBSITES_PORT=8000`. Set the health check
   path to `/health/`.

Basic B1 is billed by the hour (about $0.018 an hour in US regions when this
was written; check the Azure pricing page for your region). It's the most
work of these options. Choose it when the organisation already uses Azure.

## 8. Fly.io

`flyctl launch` in the VS Code terminal detects the `Dockerfile` and deploys
it. Fly.io has had no free tier for accounts created since October 2024: new
accounts get a short trial and need a card, and a small always-on app costs a
few dollars a month. It has no advantage over Railway for this demo.

---

## Environment variables for hosted options

| Variable | Value | Why |
|---|---|---|
| `DATABASE_URL` | From the platform's PostgreSQL | Where the data lives. The start-up script waits for this database. |
| `DEBUG` | `False` | Hides technical error pages; turns on secure cookies. |
| `HORILLA_ENV` | `production` | Turns on the production safety checks even if `DEBUG` is left on. |
| `SECRET_KEY` | Long random value | Signs sessions. The app refuses to start with a default one. |
| `DB_INIT_PASSWORD` | Random value | Required by the production checks. |
| `ALLOWED_HOSTS` | The app's hostname(s), e.g. `.up.railway.app` | Django answers other hostnames with "Bad Request". Not needed on Render. |
| `CSRF_TRUSTED_ORIGINS` | `https://` + the hostname, e.g. `https://*.up.railway.app` | Without it, signing in fails. Not needed on Render. |
| `SECURE_SSL_REDIRECT` | `True` where the platform doesn't already redirect to HTTPS | Sends visitors to the HTTPS address. |
| `TIME_ZONE` | `Asia/Kolkata` | Visits are dated in India's time. |
| `RM_SEED_DEMO_DATA` | `1` for a demo, `0` for real use | Loads the 960 demo students on the first start and adds the day's check-ins on later starts. |
| `RM_REMOVE_DEMO_DATA` | `1` for one deploy when going live | Removes the demo students on start-up, for hosts without a shell. |
| `DEMO_ADMIN_USERNAME` / `DEMO_ADMIN_PASSWORD` | `admin` / your choice | The administrator, the only sign-in. |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` | `1` / `1`–`4` | Keeps memory within small plans. |

## Moving from the demo to real use

See "Going live with real students" in `RENDER_DEPLOYMENT.md`. It applies to
every hosted option: set `RM_SEED_DEMO_DATA=0`, remove the demo data
(`RM_REMOVE_DEMO_DATA=1` for one deploy, or
`python manage.py seed_youth_centre_demo --remove` where there's a shell),
change the administrator's password and import the real register. For daily use at the centre, use a
paid plan with a database that doesn't expire, and back it up.

## Sources

Prices and limits checked on 29 September 2026; they change, so check before
paying.

- Render free plan: https://render.com/docs/free
- Render free PostgreSQL expiry: https://render.com/changelog/free-postgresql-instances-now-expire-after-30-days-previously-90
- Railway plans: https://docs.railway.com/pricing/plans and https://railway.com/pricing
- Railway health checks (`healthcheck.railway.app`): https://docs.railway.com/guides/healthchecks
- Fly.io pricing: https://fly.io/docs/about/pricing/
- VS Code port forwarding: https://code.visualstudio.com/docs/debugtest/port-forwarding
- Azure App Service Python quickstart: https://learn.microsoft.com/en-us/azure/app-service/quickstart-python
- Azure App Service Linux pricing: https://azure.microsoft.com/en-us/pricing/details/app-service/linux/
- Azure PostgreSQL on a free account: https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/how-to-deploy-on-azure-free-account
- Cloudflare quick tunnels: https://flaviocopes.com/cloudflare-quick-tunnels/
- ngrok free plan limits: https://ngrok.com/docs/pricing-limits/free-plan-limits
- GitHub Codespaces billing: https://docs.github.com/billing/managing-billing-for-github-codespaces/about-billing-for-github-codespaces
