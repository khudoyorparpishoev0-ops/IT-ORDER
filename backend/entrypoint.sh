#!/usr/bin/env bash
# Точка входа контейнера API.
# Миграции применяются под advisory-локом: при нескольких репликах
# одновременный alembic upgrade иначе конфликтует сам с собой.
set -euo pipefail

echo "Ожидание базы данных..."
for i in $(seq 1 60); do
  if python -c "
import sys
from sqlalchemy import text
from app.db.session import get_engine
try:
    with get_engine().connect() as c:
        c.execute(text('select 1'))
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    echo "База доступна."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "База не поднялась за 60 попыток." >&2
    exit 1
  fi
  sleep 1
done

echo "Применение миграций..."
python - <<'PY'
from sqlalchemy import text
from alembic import command
from alembic.config import Config
from app.db.session import get_engine

LOCK_ID = 4815162342  # произвольная константа, одна на весь проект

with get_engine().connect() as conn:
    conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_ID})
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})
        conn.commit()
PY

echo "Запуск API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
