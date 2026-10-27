#!/bin/sh
# Container entrypoint: apply migrations when a database is attached, then serve API + frontend.
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "Applying database migrations…"
  # Keep serving the map viewer if the database is misconfigured; /api/health reports "schema".
  if ! alembic upgrade head; then
    echo "WARNING: database migrations failed. Customer Data stays unavailable until the database is fixed (PostGIS is required)." >&2
  fi
else
  echo "DATABASE_URL not set; starting without a database."
fi

# Trust X-Forwarded-* from Railway's proxy (env var rather than a "*" argument, which some shells glob).
export FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers
