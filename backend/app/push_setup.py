"""Ключ для push-уведомлений одной командой.

    docker compose exec api python -m app.push_setup          # новый ключ
    docker compose exec api python -m app.push_setup --check  # что настроено

Ключ печатается строкой для .env. Смена ключа обнуляет подписки всех
телефонов: люди увидят «Включить уведомления» заново.
"""

from __future__ import annotations

import sys

from app.config import get_settings
from app.core.push import PushError, generate_private_key, public_key


def main(argv: list[str]) -> int:
    if "--check" in argv:
        settings = get_settings()
        if not settings.push_enabled:
            print("Push выключен: VAPID_PRIVATE_KEY не задан.")
            return 1
        try:
            key = public_key()
        except PushError as exc:
            print(f"VAPID_PRIVATE_KEY задан, но не годится: {exc}")
            return 1
        print(f"Push настроен. Открытый ключ: {key}")
        print(f"Контакт в подписи: {settings.push_subject}")
        return 0

    print("# Вставьте в .env — строка одна, без переносов:")
    print(f"VAPID_PRIVATE_KEY={generate_private_key()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
