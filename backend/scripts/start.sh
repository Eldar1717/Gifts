#!/usr/bin/env sh
# Production entrypoint: apply migrations, then start the API.
set -eu

echo "==> Applying database migrations"
alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "==> Seeding demo catalogue (SEED_DEMO_DATA=true)"
  python seed.py || echo "!! Seeding failed, continuing"
fi

echo "==> Starting uvicorn"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*" \
  --workers "${WEB_CONCURRENCY:-2}"
