#!/bin/bash
set -e

echo "Starting Horilla HR..."

if [ -n "${DATABASE_URL:-}" ] && [ -z "${DB_HOST:-}" ]; then
  DB_HOST="$(python -c 'from urllib.parse import urlparse; import os; print(urlparse(os.environ["DATABASE_URL"]).hostname or "")')"
  DB_PORT="$(python -c 'from urllib.parse import urlparse; import os; print(urlparse(os.environ["DATABASE_URL"]).port or 5432)')"
else
  DB_HOST="${DB_HOST:-db}"
  DB_PORT="${DB_PORT:-5432}"
fi

# Wait for PostgreSQL to be ready (with timeout)
echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
MAX_TRIES=30
COUNT=0
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  COUNT=$((COUNT + 1))
  if [ "$COUNT" -ge "$MAX_TRIES" ]; then
    echo "ERROR: PostgreSQL not available at ${DB_HOST}:${DB_PORT} after $MAX_TRIES attempts"
    exit 1
  fi
  sleep 1
done
echo "PostgreSQL is ready!"

# Every shipped default (.env.dist, docker-compose.yml's own dev default, and
# historical leaked keys) is a known, public string -- never a real secret.
# If SECRET_KEY is unset or matches one of those, generate a random one and
# persist it in the media volume so it survives container restarts instead of
# invalidating every session/JWT on each `docker compose up`.
SECRET_KEY_FILE="/app/media/.generated_secret_key"
case "${SECRET_KEY:-}" in
  ""|"django-insecure-default-key"|"dev-secret-key-change-in-production"|"django-insecure-j8op9)1q8\$1&0^s&p*_0%d#pr@w9qj@1o=3#@d=a(^@9@zd@%j"|change-me*|django-insecure-*)
    if [ -f "$SECRET_KEY_FILE" ]; then
      SECRET_KEY="$(cat "$SECRET_KEY_FILE")"
      echo "Using previously generated SECRET_KEY from $SECRET_KEY_FILE"
    else
      SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
      mkdir -p "$(dirname "$SECRET_KEY_FILE")"
      printf '%s' "$SECRET_KEY" > "$SECRET_KEY_FILE"
      chmod 600 "$SECRET_KEY_FILE"
      echo "Generated a new random SECRET_KEY and saved it to $SECRET_KEY_FILE"
    fi
    export SECRET_KEY
    ;;
esac

# Compile translation catalogs when they are missing.
#
# The image compiles .po -> .mo at build time, but the dev compose stack
# bind-mounts the source tree over /app and .mo files are not in git -- so the
# compiled catalogs are hidden and every non-English locale silently falls back
# to English. Only runs when a .po has no .mo beside it, so in the normal image
# path (already compiled) this does nothing.
if command -v msgfmt >/dev/null 2>&1; then
  if [ -n "$(find . -name '*.po' -not -path './node_modules/*' \
       -exec sh -c '[ -f "${1%.po}.mo" ] || echo x' _ {} \; 2>/dev/null | head -1)" ]; then
    echo "Compiling translation catalogs (.po -> .mo)..."
    find . -name '*.po' -not -path './node_modules/*' \
      -execdir sh -c '[ -f "${1%.po}.mo" ] || msgfmt "$1" -o "${1%.po}.mo"' _ {} \; 2>/dev/null || true
  fi
fi

# Render's free web services require a listening port while a fresh database is
# being migrated. This temporary listener keeps the deploy alive during that
# one-time release task; it is stopped before Gunicorn starts serving Django.
if [ "${RENDER_ASYNC_RELEASE_TASKS:-0}" = "1" ]; then
  echo "Opening a temporary listener while first-run release tasks complete..."
  python - "${PORT:-8000}" <<'PY' &
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys


class WaitingForSetup(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(503)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Application setup is in progress. Please retry shortly.\n")

    def log_message(self, format, *args):
        return


ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), WaitingForSetup).serve_forever()
PY
  temporary_listener_pid=$!

  cleanup_temporary_listener() {
    kill "$temporary_listener_pid" 2>/dev/null || true
    wait "$temporary_listener_pid" 2>/dev/null || true
  }
  trap cleanup_temporary_listener EXIT

  python manage.py migrate --noinput
  if [ "${RM_SEED_DEMO_DATA:-0}" = "1" ]; then
    python manage.py bootstrap_roshan_mustaqbil_demo
    python manage.py seed_youth_centre_demo
  fi
  python manage.py collectstatic --noinput --clear

  cleanup_temporary_listener
  trap - EXIT
fi

# Run migrations
#
# HORILLA_SKIP_RELEASE_TASKS=1 skips migrate and collectstatic for containers
# that share this image but must not perform release tasks -- notably the
# scheduler service, which starts alongside web. Two containers racing `migrate`
# can deadlock on the same DDL, and `collectstatic --clear` (below) would wipe
# STATIC_ROOT out from under a web container already serving from it.
if [ "${HORILLA_SKIP_RELEASE_TASKS:-0}" = "1" ]; then
  echo "HORILLA_SKIP_RELEASE_TASKS=1 -- skipping migrate and collectstatic."
  echo "Starting server..."
  exec "$@"
fi

python manage.py migrate --noinput

if [ "${RM_SEED_DEMO_DATA:-0}" = "1" ]; then
  python manage.py bootstrap_roshan_mustaqbil_demo
  python manage.py seed_youth_centre_demo
fi

# Collect static files.
#
# --clear is deliberate: STATIC_ROOT is a named volume that outlives the image,
# and plain collectstatic leaves anything it considers unmodified in place. With
# CompressedStaticFilesStorage that includes the pre-compressed .gz/.br
# siblings, so after an upgrade WhiteNoise happily served a previous release's
# global.js.gz to every browser (which all send Accept-Encoding: gzip) while
# curl, getting the identity encoding, saw the current file — JS functions
# "not defined" and half-rendered pages that looked fine to any check that
# bypassed static serving. Wiping first keeps what we serve equal to the image.
python manage.py collectstatic --noinput --clear

echo "Starting server..."
exec "$@"
