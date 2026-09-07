#!/usr/bin/env bash
# Резервная копия базы HONA CORE.
#
# Запуск с хоста, из папки проекта:
#   ./deploy/backup.sh
#
# В cron (ежедневно в 03:20, время сервера):
#   20 3 * * * cd /opt/hona-core && ./deploy/backup.sh >> data/backup.log 2>&1
#
# Дамп снимается внутри контейнера и складывается в BACKUP_PATH на хосте.
# Старые копии удаляются, чтобы не заполнить диск: на 30 ГБ это реально.
set -euo pipefail

cd "$(dirname "$0")/.."

# Значения берём из .env, не требуя его экспорта в окружение.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

BACKUP_PATH="${BACKUP_PATH:-./data/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
DB_NAME="${POSTGRES_DB:-hona_core}"
DB_USER="${POSTGRES_USER:-hona}"

mkdir -p "$BACKUP_PATH"
STAMP="$(date +%Y-%m-%d_%H-%M)"
TARGET="$BACKUP_PATH/hona_core_$STAMP.sql.gz"

echo "$(date '+%F %T') Снимаю дамп базы $DB_NAME…"

# Пишем во временный файл и переименовываем в конце: прерванный дамп
# не должен выглядеть как готовая копия.
TMP="$TARGET.part"
if ! docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists \
  | gzip -9 > "$TMP"; then
  rm -f "$TMP"
  echo "$(date '+%F %T') ОШИБКА: дамп не снят" >&2
  exit 1
fi

# Пустой или подозрительно маленький файл — тоже отказ.
SIZE=$(stat -c%s "$TMP")
if [ "$SIZE" -lt 1024 ]; then
  rm -f "$TMP"
  echo "$(date '+%F %T') ОШИБКА: дамп подозрительно мал ($SIZE б)" >&2
  exit 1
fi

mv "$TMP" "$TARGET"
echo "$(date '+%F %T') Готово: $TARGET ($((SIZE / 1024)) КБ)"

DELETED=$(find "$BACKUP_PATH" -name 'hona_core_*.sql.gz' -mtime "+$KEEP_DAYS" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
  echo "$(date '+%F %T') Удалено копий старше $KEEP_DAYS дней: $DELETED"
fi
