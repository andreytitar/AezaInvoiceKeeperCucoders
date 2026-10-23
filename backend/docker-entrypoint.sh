#!/bin/sh
set -e
cd /app
case "$1" in
  api)
    echo '{"level":"INFO","logger":"entrypoint","msg":"alembic upgrade head"}'
    alembic upgrade head
    python -m app.bootstrap
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-access-log
    ;;
  worker)
    exec python -m app.worker
    ;;
  test)
    shift
    exec python -m pytest "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
