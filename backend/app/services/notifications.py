"""Отправка уведомлений.

Письма уходят в фоне и никогда не отменяют уже совершённое действие:
заявка должна быть подана, даже если почтовый сервер недоступен.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.mail import send_quietly
from app.db.models import ExpenseRequest
from app.services import mail_templates as templates
from app.services.auth import approvers_to_notify

log = logging.getLogger(__name__)


def panel_url(path: str = "/") -> str:
    """Ссылка на раздел панели. Без PUBLIC_BASE_URL ссылки в письмах
    вести некуда, поэтому отдаём путь как есть."""
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}{path}" if base else path


def notify_new_request(session: Session, request_id: int) -> None:
    """Письмо согласующим о заявке, ждущей решения.

    Принимает id, а не объект: функция вызывается после ответа клиенту,
    когда исходная сессия уже закрыта.
    """
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    expense = session.scalar(
        select(ExpenseRequest)
        .options(
            selectinload(ExpenseRequest.employee),
            selectinload(ExpenseRequest.project),
        )
        .where(ExpenseRequest.id == request_id)
    )
    if expense is None:
        log.warning("Заявка %s исчезла до отправки уведомления", request_id)
        return

    recipients = [
        person
        for person in approvers_to_notify(session)
        # Автору не сообщаем о его же заявке.
        if person.id != expense.employee_id
    ]
    if not recipients:
        return

    for person in recipients:
        letter = templates.request_awaiting_approval(
            approver_name=person.full_name,
            employee_name=expense.employee.full_name,
            number=expense.number,
            project=expense.project.name,
            amount=expense.amount,
            url=panel_url("/approvals"),
        )
        letter.to = person.email or ""
        letter.headers["X-Entity-Ref"] = expense.number
        if letter.to:
            send_quietly(letter)

    log.info(
        "Уведомление о заявке %s отправлено %s получателям",
        expense.number,
        len(recipients),
    )
