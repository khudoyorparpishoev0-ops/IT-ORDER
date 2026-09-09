"""Отправка сообщений в Telegram.

Устроено как почта в `app/core/mail.py`: интерфейс отправки подменяется в
тестах, а неудача никогда не отменяет уже совершённое действие — заявка
должна быть подана, даже если Telegram недоступен.

HTTP-клиент здесь на стандартной библиотеке: ради одного POST в минуту
тянуть зависимость незачем.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """Сообщение не ушло. Текст — для администратора, не для сотрудника."""


@dataclass
class Message:
    """Сообщение в чат. Разметка HTML: у Telegram она прощает больше,
    чем Markdown, где незакрытая звёздочка ломает всё сообщение."""

    chat_id: int
    text: str
    #: Кнопка-ссылка под сообщением: (подпись, адрес).
    button: tuple[str, str] | None = None
    #: Кнопки выбора: (подпись, код ответа). Код возвращается боту, когда
    #: человек нажал — по нему и понятно, что он выбрал. Каждая кнопка на
    #: своей строке: русские подписи длинные, в ряд не помещаются.
    choices: list[tuple[str, str]] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


class Transport(Protocol):
    def send(self, message: Message) -> None: ...


def call(method: str, payload: dict) -> dict:
    """Вызов Bot API. Ошибку поднимает наружу — решает вызывающий.

    Токен идёт в адресе (так устроен Bot API), поэтому адрес в сообщения
    об ошибках не попадает: в логах ему не место.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise TelegramError("Токен бота не задан")

    request = urllib.request.Request(
        f"{API_BASE}/bot{settings.telegram_bot_token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.telegram_timeout_seconds
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        # 403 — человек не нажал «Старт» или заблокировал бота. Это не сбой
        # сервера, и админу знать об этом полезнее, чем видеть трассировку.
        raise TelegramError(f"Telegram отказал ({exc.code}): {detail}") from exc
    except OSError as exc:
        raise TelegramError(f"Telegram недоступен: {exc}") from exc

    if not body.get("ok"):
        raise TelegramError(f"Telegram отказал: {body.get('description')}")
    return body


class HttpTransport:
    """Настоящая отправка через Bot API."""

    def send(self, message: Message) -> None:
        payload: dict = {
            "chat_id": message.chat_id,
            "text": message.text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        rows = [[{"text": title, "callback_data": code}] for title, code in message.choices]
        if message.button:
            title, url = message.button
            rows.append([{"text": title, "url": url}])
        if rows:
            payload["reply_markup"] = {"inline_keyboard": rows}
        payload.update(message.extra)
        call("sendMessage", payload)


class NullTransport:
    """Заглушка: бот не настроен — молча ничего не делаем."""

    def send(self, message: Message) -> None:
        log.debug("Telegram не настроен, сообщение не отправлено")


_transport: Transport | None = None


def set_transport(transport: Transport | None) -> None:
    """Подмена отправки. Тесты не должны ходить в сеть."""
    global _transport
    _transport = transport


def _current() -> Transport:
    if _transport is not None:
        return _transport
    return HttpTransport() if get_settings().telegram_enabled else NullTransport()


def send(message: Message) -> None:
    """Отправка с ошибкой наружу — для проверочных сообщений."""
    _current().send(message)


def send_quietly(message: Message) -> None:
    """Отправка, которая не должна ломать основное действие.

    Заявка уже согласована; если бот молчит, это повод разобраться, но не
    повод отменять решение.
    """
    try:
        _current().send(message)
    except TelegramError as exc:
        log.warning("Не удалось отправить в Telegram: %s", exc)
    except Exception:  # noqa: BLE001
        log.exception("Неожиданная ошибка при отправке в Telegram")


def answer_callback(callback_id: str) -> None:
    """Гасит «часики» на нажатой кнопке.

    Без этого Telegram крутит ожидание на кнопке до таймаута, и человеку
    кажется, что бот завис. Ошибку глотаем: не ответить на нажатие — не
    повод ронять разбор самого нажатия.
    """
    try:
        call("answerCallbackQuery", {"callback_query_id": callback_id})
    except TelegramError as exc:
        log.debug("Не удалось погасить кнопку: %s", exc)
