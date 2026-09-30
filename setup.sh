#!/usr/bin/env bash
# Set up Roshan Mustaqbil on Linux or macOS: ./setup.sh
# (On Windows, double-click setup.bat instead.)
#
# It finds Python 3.12-3.14 (or installs 3.12 with uv, no admin rights
# needed), installs the app's packages, creates the settings file and
# database, creates the administrator and optionally loads the demo data.
# Running it again is safe: it keeps the settings, database and password.
#
# Unattended:  ./setup.sh --quiet --admin-password "choose-one" --demo no
# Then start the app with:  scripts/start.sh
set -euo pipefail

QUIET=0
ADMIN_PASSWORD="${RM_ADMIN_PASSWORD:-}"
DEMO=ask
while [ $# -gt 0 ]; do
    case "$1" in
        --quiet) QUIET=1 ;;
        --admin-password) ADMIN_PASSWORD="${2:-}"; shift ;;
        --demo) DEMO="${2:-}"; shift ;;
        -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (see ./setup.sh --help)"; exit 2 ;;
    esac
    shift
done
case "$DEMO" in ask|yes|no) ;; *) echo "--demo takes yes, no or ask"; exit 2 ;; esac

APP="$(cd "$(dirname "$0")" && pwd)"
cd "$APP"

step() { printf '\n== %s\n' "$1"; }
done_() { printf '   %s\n' "$1"; }
stop() { printf '\nSetup stopped: %s\n' "$1" >&2; exit 1; }
ask_yes_no() {  # question, default (yes/no)
    [ "$QUIET" = 1 ] && { [ "$2" = yes ]; return; }
    local hint answer
    hint=$([ "$2" = yes ] && echo "Y/n" || echo "y/N")
    read -r -p "$1 [$hint] " answer
    answer="${answer:-$2}"
    case "$answer" in [Yy]*) return 0 ;; *) return 1 ;; esac
}
venv_python() {
    if [ -x .venv/bin/python ]; then echo .venv/bin/python
    elif [ -x .venv/Scripts/python.exe ]; then echo .venv/Scripts/python.exe  # Git Bash on Windows
    fi
}

echo
echo "Roshan Mustaqbil setup"
echo "Folder: $APP"

# 1. Python ---------------------------------------------------------------------
step "1/6 Python"
# The app's packages support Python 3.12 to 3.14 (and need its headers).
suitable() {
    "$1" -c 'import os, sys, sysconfig; ok = (3, 12) <= sys.version_info[:2] <= (3, 14) and os.path.exists(os.path.join(sysconfig.get_paths()["include"], "Python.h")); sys.exit(0 if ok else 1)' 2>/dev/null
}
PYTHON=""
if [ -z "$(venv_python)" ]; then
    for candidate in python3.12 python3.13 python3.14 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && suitable "$candidate"; then
            PYTHON="$(command -v "$candidate")"
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        if ! command -v uv >/dev/null 2>&1; then
            command -v curl >/dev/null 2>&1 || stop "Python 3.12 isn't installed and curl isn't there to fetch it. Install Python 3.12 (with its development headers), then run setup again."
            echo "   Installing uv, which fetches Python 3.12 for this app only..."
            curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null || stop "Couldn't install uv. Check the internet connection and run setup again."
        fi
        uv python install 3.12 >/dev/null || stop "Couldn't install Python 3.12. Check the internet connection and run setup again."
        PYTHON="$(uv python find 3.12)"
    fi
    done_ "Using $PYTHON"
else
    done_ "Using the app's existing Python environment"
fi

# 2. The app's packages ---------------------------------------------------------
step "2/6 The app's packages (the first time takes 5-15 minutes)"
if [ -z "$(venv_python)" ]; then
    "$PYTHON" -m venv .venv || stop "Couldn't create the Python environment (.venv). On Debian or Ubuntu: sudo apt install python3.12-venv"
fi
VENV="$(venv_python)"
"$VENV" -m pip install --upgrade --quiet pip || stop "Couldn't update pip. Check the internet connection and run setup again."
if ! "$VENV" -m pip install --quiet --disable-pip-version-check -r requirements.txt; then
    echo "   Retrying once..."
    "$VENV" -m pip install --disable-pip-version-check -r requirements.txt || stop "Couldn't install the app's packages. Check the internet connection and run setup again."
fi
done_ "Packages installed"

# 3. Settings -------------------------------------------------------------------
step "3/6 Settings"
if [ -f .env ]; then
    done_ "Keeping the existing settings file (.env)"
else
    # Letters, digits, - and _ only: a "$" would be read as a reference to another setting.
    secret="$("$VENV" -c 'import secrets; print(secrets.token_urlsafe(50))')"
    init_password="$("$VENV" -c 'import secrets; print(secrets.token_urlsafe(24))')"
    hosts="localhost,127.0.0.1,$(hostname | tr '[:upper:]' '[:lower:]')"
    addresses="$( (hostname -I 2>/dev/null || ipconfig getifaddr en0 2>/dev/null || true) | tr ' ' '\n' | grep -E '^[0-9]+(\.[0-9]+){3}$' | grep -v '^127\.' || true)"
    for address in $addresses; do hosts="$hosts,$address"; done
    hosts="$hosts,.devtunnels.ms,.trycloudflare.com,.ngrok-free.app,.ngrok-free.dev,.app.github.dev"
    umask 077
    cat > .env <<EOF
# Roshan Mustaqbil settings for this machine, written by setup. Keep this file private.
DEBUG=True
SECRET_KEY=$secret
ALLOWED_HOSTS=$hosts
CSRF_TRUSTED_ORIGINS=http://localhost:8001,http://127.0.0.1:8001,https://*.devtunnels.ms,https://*.trycloudflare.com,https://*.ngrok-free.app,https://*.ngrok-free.dev,https://*.app.github.dev
TIME_ZONE=Asia/Kolkata
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=$APP/roshan_mustaqbil.sqlite3
DB_INIT_PASSWORD=$init_password
EOF
    umask 022
    done_ "Created .env (database: roshan_mustaqbil.sqlite3)"
fi

# 4. Database -------------------------------------------------------------------
step "4/6 Database (the first time takes a few minutes)"
"$VENV" manage.py migrate --noinput -v 0 || stop "Couldn't set up the database."
done_ "Database ready"

# 5. The administrator ----------------------------------------------------------
step "5/6 The administrator (the only sign-in)"
exists="$("$VENV" manage.py shell -c "from horilla_auth.models import HorillaUser; print('yes' if HorillaUser.objects.filter(username='admin').exists() else 'no')" 2>/dev/null | tail -n 1 || true)"
if [ "$exists" = yes ]; then
    # Nothing to ask: setup never changes an existing password. This still
    # checks the centre's records; the throwaway password is not used.
    "$VENV" manage.py bootstrap_roshan_mustaqbil_demo --password "$("$VENV" -c 'import secrets; print(secrets.token_urlsafe(24))')" || stop "Couldn't check the administrator."
    done_ "Keeping the existing administrator, admin, and their password. To change it: .venv/bin/python manage.py changepassword admin"
else
    if [ -z "$ADMIN_PASSWORD" ]; then
        [ "$QUIET" = 1 ] && stop "Give --admin-password (or set RM_ADMIN_PASSWORD) for an unattended setup."
        while true; do
            read -r -s -p "Choose the administrator's password (8+ characters): " first; echo
            read -r -s -p "Type it again: " second; echo
            if [ "${#first}" -lt 8 ]; then echo "   Use at least 8 characters."; continue; fi
            if [ "$first" != "$second" ]; then echo "   The two passwords don't match."; continue; fi
            ADMIN_PASSWORD="$first"
            break
        done
    fi
    "$VENV" manage.py bootstrap_roshan_mustaqbil_demo --password "$ADMIN_PASSWORD" || stop "Couldn't create the administrator."
    done_ "Sign in as: admin, with the password you chose"
fi

# 6. Demo data ------------------------------------------------------------------
step "6/6 Demo data"
load_demo=no
case "$DEMO" in
    yes) load_demo=yes ;;
    ask) ask_yes_no "Load the demo data (960 example students)? Choose No for real use." no && load_demo=yes ;;
esac
if [ "$load_demo" = yes ]; then
    "$VENV" manage.py seed_youth_centre_demo || stop "Couldn't load the demo data."
    done_ "Demo data loaded. Remove it before real use: .venv/bin/python manage.py seed_youth_centre_demo --remove"
else
    done_ "No demo data. Add students at the desk, or import your register (Students > Import from a spreadsheet)."
fi

echo
echo "Setup finished."
echo "Start the app with: scripts/start.sh"
echo "then open http://127.0.0.1:8001 and sign in as admin."
