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


def request_url(request: ExpenseRequest) -> str:
    """Ссылка на карточку заявки. Уведомление ведёт к самой заявке, а не
    в раздел: со списка человеку ещё искать нужную строку, а на телефоне
    после входа он должен оказаться там, куда его позвали."""
    return panel_url(f"/requests/{request.id}")


def _load(session: Session, request_id: int) -> ExpenseRequest | None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    return session.scalar(
        select(ExpenseRequest)
        .options(
            selectinload(ExpenseRequest.employee),
            selectinload(ExpenseRequest.project),
        )
        .where(ExpenseRequest.id == request_id)
    )


def notify_sourcing(session: Session, request_id: int) -> None:
    """Письмо отделу закупа: потребность согласована, нужна оценка."""
    from app.core.permissions import Permission
    from app.services.auth import notifiable_by_permission

    expense = _load(session, request_id)
    if expense is None:
        return

    for person in notifiable_by_permission(session, Permission.SOURCE_REQUEST):
        if person.id == expense.employee_id:
            continue
        letter = templates.request_for_procurement(
            buyer_name=person.full_name,
            employee_name=expense.employee.full_name,
            number=expense.number,
            project=expense.project.name,
            url=request_url(expense),
        )
        letter.to = person.email or ""
        letter.headers["X-Entity-Ref"] = expense.number
        if letter.to:
            send_quietly(letter)


def notify_priced(session: Session, request_id: int) -> None:
    """Письмо руководителю: закуп вернул заявку с суммой."""
    from app.core.permissions import Permission
    from app.services.auth import notifiable_by_permission

    expense = _load(session, request_id)
    if expense is None:
        return

    for person in notifiable_by_permission(session, Permission.DECIDE_REQUEST):
        if person.id == expense.employee_id:
            continue
        letter = templates.request_awaiting_approval(
            approver_name=person.full_name,
            employee_name=expense.employee.full_name,
            number=expense.number,
            project=expense.project.name,
            amount=expense.amount,
            url=request_url(expense),
            stage="Закуп оценил заявку, нужна ваша подпись под суммой",
        )
        letter.to = person.email or ""
        letter.headers["X-Entity-Ref"] = expense.number
        if letter.to:
            send_quietly(letter)


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
            # Суммы на этом шаге нет: согласуется сама покупка.
            amount=None,
            url=request_url(expense),
            stage="Новая заявка на согласование покупки",
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
