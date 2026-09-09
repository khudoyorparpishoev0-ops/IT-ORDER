#!/usr/bin/env bash
# Восстановление базы HONA ORDER из копии.
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

# Значения берём из .env, не загружая его в shell целиком: файл написан
# для docker compose, и значение с пробелом без кавычек
# (MAIL_FROM_NAME=IT-HONA ORDER) bash выполнил бы как команду. Читаем
# только нужные ключи; при повторе ключа берём последний, как compose.
env_value() {
  [ -f .env ] || return 0
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- \
    | sed -e 's/\r$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

DB_NAME="$(env_value POSTGRES_DB)"; DB_NAME="${DB_NAME:-hona_core}"
DB_USER="$(env_value POSTGRES_USER)"; DB_USER="${DB_USER:-hona}"

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
