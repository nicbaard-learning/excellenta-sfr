#!/usr/bin/env bash
set -e

echo "=== Running database migrations ==="
alembic upgrade head

echo "=== Starting application server ==="
exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-4} \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
