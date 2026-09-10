"""Отправка сводок в Telegram. Устойчивая: сбой не роняет рассылку.

Правило то же, что у писем и обычных сообщений бота: неудача одного
получателя не отменяет остальных и не роняет планировщик. Бесконечных
переотправок нет — недоставленная сводка видна в метриках и разбирается
человеком, а цикл переотправки при упавшем Telegram разбудил бы всех
дважды, когда он поднимется.

Канал на этом этапе один. Появится второй — он появится здесь, а
`intelligence.py` останется как есть: он решает «кому и когда», а не
«как именно доставить».
"""

from __future__ import annotations

import logging

from app.core.telegram import Message, TelegramError
from app.core.telegram import send as telegram_send
from app.db.models import Employee

log = logging.getLogger(__name__)


def can_deliver(employee: Employee) -> bool:
    """Есть ли куда отправлять. Отвязанный чат — не ошибка, а выбор."""
    return bool(employee.active and employee.telegram_chat_id)


def send(
    employee: Employee,
    text: str,
    *,
    button: tuple[str, str] | None = None,
    choices: list[tuple[str, str]] | None = None,
) -> str | None:
    """Отправляет сообщение. Возвращает текст ошибки или None при удаче.

    Ошибку возвращаем, а не глотаем: вызывающему она нужна для истории
    доставок — по ней потом видно, сколько сводок не дошло и почему.
    Наружу исключение не пускаем: следующий получатель не виноват в том,
    что этот заблокировал бота.
    """
    if not can_deliver(employee):
        return "Telegram не подключён"
    try:
        telegram_send(
            Message(
                chat_id=int(employee.telegram_chat_id),
                text=text,
                button=button,
                choices=choices or [],
            )
        )
    except TelegramError as exc:
        log.warning("Сводка не дошла до %s: %s", employee.full_name, exc)
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        log.exception("Неожиданная ошибка при отправке сводки")
        return f"{type(exc).__name__}: {exc}"
    return None
