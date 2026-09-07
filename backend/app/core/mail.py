"""Отправка почты через SMTP (у нас — Zoho Mail).

Письма уходят в фоне: SMTP-соединение занимает секунды, и держать на нём
HTTP-запрос нельзя. Неудача отправки логируется и не роняет действие —
заявка должна быть согласована, даже если письмо не ушло.

Пароли и тела писем в логи не пишутся.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.headerregistry import Address
from email.message import EmailMessage
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class MailError(Exception):
    """Письмо не отправлено."""


@dataclass(slots=True)
class Letter:
    """Письмо. Текстовая часть обязательна: почтовые клиенты и фильтры
    относятся к письмам без неё хуже."""

    to: str
    subject: str
    text: str
    html: str | None = None
    #: Заголовки для диагностики, например X-Entity-Ref.
    headers: dict[str, str] = field(default_factory=dict)


class Transport(Protocol):
    """Способ доставки. Подменяется в тестах, чтобы не ходить в сеть."""

    def send(self, message: EmailMessage) -> None: ...


class SmtpTransport:
    """Доставка через SMTP. Zoho принимает и SSL (465), и STARTTLS (587)."""

    def send(self, message: EmailMessage) -> None:
        settings = get_settings()
        context = ssl.create_default_context()
        try:
            if settings.smtp_security == "ssl":
                with smtplib.SMTP_SSL(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                    context=context,
                ) as server:
                    server.login(settings.smtp_user, settings.smtp_password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                ) as server:
                    server.starttls(context=context)
                    server.login(settings.smtp_user, settings.smtp_password)
                    server.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            # Частая причина у Zoho: обычный пароль вместо пароля приложения
            # либо сервер не того региона.
            raise MailError(
                "SMTP отклонил аутентификацию. Проверьте, что задан пароль "
                "приложения Zoho и указан сервер вашего региона."
            ) from exc
        except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
            raise MailError(f"Не удалось отправить письмо: {type(exc).__name__}") from exc


class NullTransport:
    """Почта не настроена: письмо только логируется.

    Так система остаётся работоспособной без SMTP — просто без писем.
    """

    def send(self, message: EmailMessage) -> None:
        log.warning(
            "Почта не настроена, письмо не отправлено: «%s» → %s",
            message["Subject"],
            message["To"],
        )


_transport: Transport | None = None


def set_transport(transport: Transport | None) -> None:
    """Подменяет способ доставки. Используется в тестах."""
    global _transport
    _transport = transport


def get_transport() -> Transport:
    if _transport is not None:
        return _transport
    return SmtpTransport() if get_settings().mail_enabled else NullTransport()


def build_message(letter: Letter) -> EmailMessage:
    settings = get_settings()
    message = EmailMessage()
    message["Subject"] = letter.subject
    message["To"] = letter.to

    sender = settings.mail_sender
    local, _, domain = sender.partition("@")
    if domain:
        message["From"] = Address(settings.mail_from_name, local, domain)
    else:
        message["From"] = sender

    for name, value in letter.headers.items():
        message[name] = value

    message.set_content(letter.text)
    if letter.html:
        message.add_alternative(letter.html, subtype="html")
    return message


def send(letter: Letter) -> None:
    """Отправляет письмо. Ошибку поднимает наверх — решает вызывающий."""
    get_transport().send(build_message(letter))


def send_quietly(letter: Letter) -> None:
    """Отправляет и глушит ошибку.

    Для уведомлений: неудача письма не должна отменять уже совершённое
    действие. В журнал ошибка попадает, адресат — нет.
    """
    try:
        send(letter)
    except MailError as exc:
        log.error("Уведомление «%s» не отправлено: %s", letter.subject, exc)
