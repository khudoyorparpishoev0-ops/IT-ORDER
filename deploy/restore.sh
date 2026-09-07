#!/usr/bin/env bash
# Восстановление базы HONA CORE из копии.
#
#   ./deploy/restore.sh data/backups/hona_core_2026-09-07_03-20.sql.gz
#
# ВНИМАНИЕ: текущее содержимое базы будет заменено. Скрипт спрашивает
# подтверждение, потому что отменить это нельзя.
set -euo pipefail

cd "$(dirname "$0")/.."

DUMP="${1:-}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "Укажите файл копии: ./deploy/restore.sh data/backups/hona_core_*.sql.gz" >&2
  exit 1
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

DB_NAME="${POSTGRES_DB:-hona_core}"
DB_USER="${POSTGRES_USER:-hona}"

echo "Из копии: $DUMP"
echo "В базу:   $DB_NAME"
echo
echo "Текущие данные будут ЗАМЕНЕНЫ. Отменить восстановление нельзя."
read -r -p "Продолжить? Введите «да»: " ANSWER
if [ "$ANSWER" != "да" ]; then
  echo "Отменено."
  exit 1
fi

# API останавливаем: иначе он пишет в базу во время восстановления.
echo "Останавливаю api…"
docker compose stop api

echo "Восстанавливаю…"
gunzip -c "$DUMP" | docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1

echo "Запускаю api…"
docker compose start api

echo "Готово. Проверьте /health и вход в панель."
