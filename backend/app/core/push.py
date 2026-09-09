"""Push-уведомления в браузер (Web Push, RFC 8030 + VAPID).

Устроено как Telegram в `app/core/telegram.py`: транспорт подменяется в
тестах, неудача никогда не отменяет уже совершённое действие. Отличие
одно: подписка может умереть — человек снял приложение с экрана,
переустановил браузер. Сервер push-службы отвечает на это 404 или 410, и
такую подписку нужно удалить, иначе она будет молча отказывать вечно.
Для этого транспорт различает `PushGone` и остальные ошибки.

Ключи VAPID — пара EC P-256. Хранится только закрытый ключ
(`VAPID_PRIVATE_KEY`), открытый выводится из него: два ключа в .env —
это две возможности их перепутать.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class PushError(RuntimeError):
    """Уведомление не ушло. Текст — для администратора."""


class PushGone(PushError):
    """Подписка больше не действует: удалить и забыть."""


@dataclass
class Notification:
    """Что показать на телефоне. Ссылка открывается по нажатию."""

    #: Подписка браузера: {"endpoint": ..., "keys": {"p256dh": ..., "auth": ...}}
    subscription: dict
    title: str
    body: str
    url: str = "/"
    #: Одинаковый tag заменяет предыдущее уведомление, а не копит их.
    tag: str | None = None
    extra: dict = field(default_factory=dict)

    def payload(self) -> str:
        data = {"title": self.title, "body": self.body, "url": self.url}
        if self.tag:
            data["tag"] = self.tag
        data.update(self.extra)
        return json.dumps(data, ensure_ascii=False)


class Transport(Protocol):
    def send(self, notification: Notification) -> None: ...


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_key() -> str:
    """Открытый ключ VAPID в том виде, какой ждёт браузер
    (`applicationServerKey`: точка P-256 без сжатия, base64url)."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    settings = get_settings()
    if not settings.vapid_private_key:
        raise PushError("VAPID_PRIVATE_KEY не задан")
    try:
        vapid = Vapid.from_string(settings.vapid_private_key)
    except Exception as exc:  # noqa: BLE001 — py_vapid бросает разное
        raise PushError(f"VAPID_PRIVATE_KEY не разбирается: {exc}") from exc
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64url(raw)


def generate_private_key() -> str:
    """Новый закрытый ключ для .env. Вызывается из `python -m app.push_setup`."""
    from cryptography.hazmat.primitives.asymmetric import ec

    # Ключ делаем сами, а не через py_vapid: его generate_keys передаёт в
    # cryptography класс кривой вместо экземпляра и получает предупреждение
    # об устаревании, которое скоро станет ошибкой.
    private = ec.generate_private_key(ec.SECP256R1())
    raw = private.private_numbers().private_value.to_bytes(32, "big")
    return _b64url(raw)


class HttpTransport:
    """Настоящая отправка через push-службу браузера (Google, Apple, Mozilla)."""

    def send(self, notification: Notification) -> None:
        from pywebpush import WebPushException, webpush

        settings = get_settings()
        try:
            webpush(
                subscription_info=notification.subscription,
                data=notification.payload(),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.push_subject},
                ttl=settings.push_ttl_seconds,
                timeout=settings.push_timeout_seconds,
            )
        except WebPushException as exc:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            if status in (404, 410):
                raise PushGone(f"подписка отозвана ({status})") from exc
            detail = ""
            if response is not None:
                detail = (getattr(response, "text", "") or "")[:200]
            raise PushError(f"push-служба отказала ({status}): {detail or exc}") from exc
        except OSError as exc:
            raise PushError(f"push-служба недоступна: {exc}") from exc


class NullTransport:
    """Заглушка: ключи не заданы — молча ничего не делаем."""

    def send(self, notification: Notification) -> None:
        log.debug("Push не настроен, уведомление не отправлено")


_transport: Transport | None = None


def set_transport(transport: Transport | None) -> None:
    """Подмена отправки. Тесты не должны ходить в сеть."""
    global _transport
    _transport = transport


def _current() -> Transport:
    if _transport is not None:
        return _transport
    return HttpTransport() if get_settings().push_enabled else NullTransport()


def send(notification: Notification) -> None:
    """Отправка с ошибкой наружу — для проверочного уведомления."""
    _current().send(notification)


def send_quietly(notification: Notification) -> bool:
    """Отправка, которая не должна ломать основное действие.

    Возвращает False, если подписка мертва и её пора удалить; остальные
    ошибки только в лог.
    """
    try:
        _current().send(notification)
    except PushGone as exc:
        log.info("Push-подписка отозвана: %s", exc)
        return False
    except PushError as exc:
        log.warning("Не удалось отправить push: %s", exc)
    except Exception:  # noqa: BLE001
        log.exception("Неожиданная ошибка при отправке push")
    return True
