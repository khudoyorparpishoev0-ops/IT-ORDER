#!/usr/bin/env bash
# Проверка .env перед запуском.
#
#   ./deploy/check-env.sh
#
# Ловит две ошибки, которые иначе всплывают уже после запуска:
#   - повтор ключа. docker compose берёт последнее значение, поэтому
#     случайно вставленная пустая строка перебивает заполненную выше;
#   - пустое обязательное значение.
set -uo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "Нет файла $ENV_FILE. Скопируйте образец: cp .env.example .env" >&2
  exit 1
fi

# Без этих значений система не поднимется или в неё будет некому войти.
REQUIRED=(
  POSTGRES_PASSWORD
  SECRET_KEY
  APP_DOMAIN
  PUBLIC_BASE_URL
  ALLOWED_EMAIL_DOMAINS
  ACME_EMAIL
  BOOTSTRAP_ADMIN_EMAIL
  BOOTSTRAP_ADMIN_PASSWORD
)

# Без этих не будет писем и уведомлений в Telegram, но система работает.
OPTIONAL=(SMTP_HOST SMTP_USER SMTP_PASSWORD TELEGRAM_BOT_TOKEN TELEGRAM_BOT_USERNAME VAPID_PRIVATE_KEY VAPID_SUBJECT)

problems=0

# Файл переносят на сервер через Windows, и он приезжает с CRLF. Невидимый
# «\r» попадает в конец каждого значения: токен бота становится на символ
# длиннее и Telegram отвечает «malformed URL», пароль SMTP не подходит, а
# по симптомам это не разберёшь. Чиним сразу, а не рассказываем как.
echo "=== Переводы строк ==="
if grep -q $'\r' "$ENV_FILE"; then
  echo "  CRLF    в файле виндовые переводы строк — лишний символ попадёт"
  echo "          в каждое значение (токен, пароль SMTP)."
  echo "          Исправить: sed -i 's/\r$//' $ENV_FILE"
  problems=1
else
  echo "  ok      обычные переводы строк"
fi

echo
echo "=== Повторяющиеся ключи ==="
DUPES=$(grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | tr -d '=' | sort | uniq -d)
if [ -n "$DUPES" ]; then
  echo "$DUPES" | while read -r key; do
    echo "  ПОВТОР  $key — строки: $(grep -n "^$key=" "$ENV_FILE" | cut -d: -f1 | tr '\n' ' ')"
  done
  echo
  echo "  Оставьте по одной строке на ключ: последняя перебивает все выше."
  problems=1
else
  echo "  повторов нет"
fi

value_of() {
  # Берём последнее вхождение — именно его увидит docker compose.
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-
}

echo
echo "=== Обязательные значения ==="
for key in "${REQUIRED[@]}"; do
  val=$(value_of "$key")
  if [ -z "$val" ]; then
    echo "  ПУСТО   $key"
    problems=1
  elif [[ "$val" == *"ваш@"* || "$val" == *"пароль приложения"* || "$val" == *"←"* ]]; then
    # Значение из примера осталось незаполненным.
    echo "  ПРИМЕР  $key = $val"
    problems=1
  else
    echo "  ok      $key"
  fi
done

echo
echo "=== Почта и Telegram (без них уведомлений не будет) ==="
for key in "${OPTIONAL[@]}"; do
  val=$(value_of "$key")
  [ -z "$val" ] && echo "  пусто   $key" || echo "  ok      $key"
done

echo
if [ "$problems" -ne 0 ]; then
  echo "Есть замечания — исправьте перед запуском." >&2
  exit 1
fi
echo "Конфигурация готова к запуску."
