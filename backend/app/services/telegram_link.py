"""Привязка Telegram к сотруднику.

Человек нажимает в панели «Подключить», получает ссылку
https://t.me/<бот>?start=<код> и открывает её. Бот присылает нам этот код
вместе с id чата — так мы узнаём, кому писать, не спрашивая ни у кого
внутренних идентификаторов.

Код одноразовый и живёт полчаса: ссылку могут переслать, а привязка чужого
чата к чужой учётной записи — это чужие уведомления о деньгах.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ConflictError, ValidationError
from app.core.time import utcnow
from app.db.models import Employee
from app.services.audit import write_audit

log = logging.getLogger(__name__)

#: Сколько живёт код привязки.
LINK_TTL_MINUTES = 30


def start_link(session: Session, employee: Employee) -> dict[str, str]:
    """Готовит код и ссылку на бота."""
    settings = get_settings()
    if not settings.telegram_enabled:
        raise ValidationError(
            "Telegram не настроен: администратор должен задать TELEGRAM_BOT_TOKEN"
        )
    if not settings.telegram_bot_username:
        raise ValidationError(
            "Не задано имя бота (TELEGRAM_BOT_USERNAME) — ссылку не собрать"
        )

    code = secrets.token_urlsafe(12)[:16]
    employee.telegram_link_code = code
    employee.telegram_link_expires_at = utcnow() + timedelta(minutes=LINK_TTL_MINUTES)
    session.flush()

    return {
        "code": code,
        "url": f"https://t.me/{settings.telegram_bot_username}?start={code}",
        "expires_in_minutes": str(LINK_TTL_MINUTES),
    }


def complete_link(
    session: Session, code: str, *, chat_id: int, username: str | None
) -> Employee | None:
    """Завершает привязку по коду из сообщения боту.

    Возвращает сотрудника или None, если код неизвестен или просрочен —
    боту в обоих случаях отвечаем одинаково, чтобы перебором кодов нельзя
    было узнать, какие из них существуют.
    """
    code = (code or "").strip()
    if not code:
        return None

    employee = session.scalar(
        select(Employee).where(Employee.telegram_link_code == code)
    )
    if employee is None or not employee.active:
        return None
    if (
        employee.telegram_link_expires_at is None
        or employee.telegram_link_expires_at < utcnow()
    ):
        return None

    # Чат уже привязан к другому человеку — молча переносить нельзя:
    # у одного из них уведомления пропадут без объяснения.
    taken = session.scalar(
        select(Employee).where(
            Employee.telegram_chat_id == chat_id, Employee.id != employee.id
        )
    )
    if taken is not None:
        raise ConflictError(
            f"Этот чат уже привязан к сотруднику {taken.full_name}. "
            "Сначала отключите Telegram у него."
        )

    employee.telegram_chat_id = chat_id
    employee.telegram_username = (username or "")[:64] or None
    employee.telegram_linked_at = utcnow()
    employee.telegram_link_code = None
    employee.telegram_link_expires_at = None

    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="telegram_linked",
        employee=employee,
        details=f"@{employee.telegram_username}" if employee.telegram_username else None,
    )
    session.flush()
    log.info("Telegram привязан сотруднику %s", employee.id)
    return employee


def unlink(session: Session, employee: Employee, *, actor: str | None = None) -> Employee:
    """Отключает уведомления в Telegram."""
    employee.telegram_chat_id = None
    employee.telegram_username = None
    employee.telegram_linked_at = None
    employee.telegram_link_code = None
    employee.telegram_link_expires_at = None
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="telegram_unlinked",
        employee=employee,
        username=actor,
    )
    session.flush()
    return employee


def by_chat(session: Session, chat_id: int) -> Employee | None:
    return session.scalar(select(Employee).where(Employee.telegram_chat_id == chat_id))
