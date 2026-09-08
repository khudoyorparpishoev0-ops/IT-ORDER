"""Настройка и проверка бота одной командой.

    docker compose exec api python -m app.telegram_setup          # настроить
    docker compose exec api python -m app.telegram_setup --check  # только проверить

Кнопка в панели делает то же самое, но до панели нужно ещё добраться, а
при разборе «почему бот молчит» важно получить ответ на одном экране и не
собирать адрес вебхука руками из токена и SECRET_KEY.
"""

from __future__ import annotations

import sys

from app.config import get_settings
from app.core.telegram import TelegramError, call

#: Что делать, когда Telegram отвечает отказом. Коды его же.
HINTS = {
    404: (
        "Telegram не знает такой токен. Возьмите действующий у @BotFather:\n"
        "  /mybots → выберите бота → API Token,\n"
        "и впишите его в .env строкой TELEGRAM_BOT_TOKEN= (без слова «bot» впереди)."
    ),
    401: "Токен отозван или неверен. Перевыпустите его у @BotFather.",
}


def _mask(url: str) -> str:
    """Прячет секрет в адресе вебхука: его печатать незачем."""
    head, _, tail = url.rpartition("/")
    return f"{head}/{tail[:4]}…{tail[-2:]}" if tail else url


def _fail(text: str) -> int:
    print(f"НЕ ГОТОВО. {text}")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    check_only = "--check" in args
    settings = get_settings()

    if not settings.telegram_bot_token:
        return _fail(
            "Токен бота не задан: строка TELEGRAM_BOT_TOKEN в .env пустая.\n"
            "Возьмите токен у @BotFather (/mybots → API Token), впишите в .env\n"
            "и пересоздайте контейнер: docker compose up -d --force-recreate api"
        )

    try:
        me = call("getMe", {})["result"]
    except TelegramError as exc:
        code = next((c for c in HINTS if f"({c})" in str(exc)), None)
        hint = HINTS.get(code, "Проверьте, что сервер имеет выход в интернет.")
        return _fail(f"Telegram не принял токен.\n{exc}\n\n{hint}")

    print(f"Бот: @{me.get('username')} ({me.get('first_name')})")
    if settings.telegram_bot_username and settings.telegram_bot_username.lstrip(
        "@"
    ) != me.get("username"):
        # Имя из .env идёт в ссылку привязки: разойдётся — человек попадёт
        # не к тому боту и «Старт» ничего не даст.
        print(
            f"  ВНИМАНИЕ: в .env TELEGRAM_BOT_USERNAME={settings.telegram_bot_username},"
            f" а бот называется @{me.get('username')}. Ссылка привязки поведёт не туда."
        )

    if not settings.public_base_url:
        return _fail("Не задан PUBLIC_BASE_URL — Telegram некуда слать обновления.")

    url = (
        f"{settings.public_base_url.rstrip('/')}"
        f"/api/telegram/webhook/{settings.telegram_webhook_secret}"
    )

    if not check_only:
        try:
            call("setWebhook", {"url": url, "allowed_updates": ["message"]})
        except TelegramError as exc:
            return _fail(f"Вебхук не установлен.\n{exc}")
        print(f"Вебхук установлен: {_mask(url)}")

    try:
        info = call("getWebhookInfo", {})["result"]
    except TelegramError as exc:
        return _fail(f"Не удалось спросить состояние вебхука.\n{exc}")

    current = info.get("url") or ""
    if not current:
        return _fail("Вебхук не установлен. Запустите команду без --check.")
    if current != url:
        print(f"  ВНИМАНИЕ: Telegram шлёт на другой адрес: {_mask(current)}")

    pending = info.get("pending_update_count", 0)
    error = info.get("last_error_message")
    if error:
        print(f"  Последняя ошибка доставки: {error}")
        print("  Проверьте, что панель открывается снаружи по https.")
    print(f"  Необработанных обновлений: {pending}")

    print("\nГОТОВО. Напишите боту /start — он должен ответить.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
