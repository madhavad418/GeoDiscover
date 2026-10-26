#!/bin/sh
# Container entrypoint: apply migrations when a database is attached, then serve API + frontend.
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "Applying database migrations…"
  alembic upgrade head
else
  echo "DATABASE_URL not set; starting without a database."
fi

# Trust X-Forwarded-* from Railway's proxy (env var rather than a "*" argument, which some shells glob).
export FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers
