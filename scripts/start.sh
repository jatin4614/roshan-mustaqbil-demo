#!/usr/bin/env bash
# Start Roshan Mustaqbil on Linux or macOS (on Windows, use scripts\start.bat).
#
#   scripts/start.sh
#
# With demo data loaded, adds today's check-ins and check-outs so far. Checks
# the data, then runs the app on http://127.0.0.1:8001 (RM_PORT changes the
# port), reachable from other devices on the network. Press Ctrl+C to stop it.
set -uo pipefail
cd "$(dirname "$0")/.."
PORT="${RM_PORT:-8001}"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
else
    echo "Can't find the app's Python environment. Set up the app first: ./setup.sh"
    exit 1
fi

echo
echo " Roshan Mustaqbil"
echo " ---------------"
echo " Adding today's demo check-ins so far (only if demo data is loaded)..."
"$PY" manage.py seed_youth_centre_demo --top-up
echo
echo " Checking the data..."
"$PY" manage.py review_rm || { echo; echo " The data check found a problem, listed above. The app will still start."; }
echo
echo " Open http://127.0.0.1:$PORT and sign in as admin. Press Ctrl+C to stop the app."
exec "$PY" manage.py runserver "0.0.0.0:$PORT" --noreload
