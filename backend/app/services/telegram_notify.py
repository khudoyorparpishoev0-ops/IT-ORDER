"""Уведомления в Telegram о судьбе заявки.

Автор получает каждое изменение: подал — и дальше видит, где заявка и что
с ней стало. Те, к кому заявка пришла, получают сообщение, что она у них.
Никаких сумм в личных чатах сверх того, что человек и так видит в панели.
"""

from __future__ import annotations

import logging
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.money import money
from app.core.telegram import Message, send_quietly
from app.db.models import Employee, ExpenseRequest, RequestStatus
from app.services.notifications import panel_url

log = logging.getLogger(__name__)

#: Что написать автору на каждом шаге. Ключ — новый статус заявки.
AUTHOR_TEXT: dict[RequestStatus, str] = {
    RequestStatus.PENDING: "отправлена на согласование покупки",
    RequestStatus.SOURCING: "согласована руководителем и передана в отдел закупа",
    RequestStatus.PRICED: "оценена закупом, сумма ушла руководителю на утверждение",
    RequestStatus.APPROVED: "утверждена, передана в бухгалтерию на оплату",
    RequestStatus.PAID: "оплачена",
    RequestStatus.FULFILLED: "закрыта: всё нашлось на складе",
    RequestStatus.REJECTED: "отклонена",
}

#: Кого зовём, когда заявка легла на их шаг.
ACTOR_TEXT: dict[str, str] = {
    "manager": "ждёт вашего решения",
    "procurement": "ждёт оценки: проверьте склад и проставьте цены",
    "finance": "утверждена и ждёт выплаты",
}

#: Куда ведёт кнопка под сообщением.
STAGE_PATH: dict[str, str] = {
    "manager": "/approvals",
    "procurement": "/sourcing",
    "finance": "/requests?status=approved",
}


def _load(session: Session, request_id: int) -> ExpenseRequest | None:
    return session.scalar(
        select(ExpenseRequest)
        .options(
            selectinload(ExpenseRequest.employee),
            selectinload(ExpenseRequest.project),
        )
        .where(ExpenseRequest.id == request_id)
    )


def _headline(request: ExpenseRequest) -> str:
    parts = [f"<b>{escape(request.number)}</b>", escape(request.project.name)]
    if request.status in (
        RequestStatus.PRICED,
        RequestStatus.APPROVED,
        RequestStatus.PAID,
    ):
        parts.append(f"{money(request.amount)} сомони")
    return " · ".join(parts)


def notify_request_state(session: Session, request_id: int) -> None:
    """Сообщает автору, что стало с его заявкой, и зовёт того, кто следующий.

    Принимает id, а не объект: вызывается из фоновой задачи, когда сессия
    запроса уже закрыта.
    """
    from app.core.permissions import Permission, has_permission
    from app.services.requests import awaiting_stage

    request = _load(session, request_id)
    if request is None:
        return

    author = request.employee
    what = AUTHOR_TEXT.get(request.status)
    to_author = False
    invited = 0
    if author is not None and author.telegram_chat_id and what:
        to_author = True
        text = (
            f"Ваша заявка {_headline(request)}\n"
            f"{escape(what.capitalize())}."
        )
        if request.status is RequestStatus.REJECTED and request.decision_comment:
            text += f"\n\nПричина: {escape(request.decision_comment)}"
        send_quietly(
            Message(
                chat_id=author.telegram_chat_id,
                text=text,
                button=("Открыть заявку", panel_url("/requests")),
            )
        )

    stage = awaiting_stage(request)
    invite = ACTOR_TEXT.get(stage)
    if not invite:
        _log_result(request, stage, to_author=to_author, invited=invited)
        return

    permission = {
        "manager": Permission.DECIDE_REQUEST,
        "procurement": Permission.SOURCE_REQUEST,
        "finance": Permission.PAY_REQUEST,
    }[stage]

    recipients = session.scalars(
        select(Employee).where(
            Employee.active.is_(True),
            Employee.telegram_chat_id.is_not(None),
            Employee.notify_new_requests.is_(True),
        )
    )
    for person in recipients:
        # Свою заявку человек не двигает — и звать его незачем.
        if person.id == request.employee_id:
            continue
        if not has_permission(person.role, permission):
            continue
        send_quietly(
            Message(
                chat_id=person.telegram_chat_id,
                text=(
                    f"Заявка {_headline(request)}\n"
                    f"{escape(request.employee.full_name)} — {escape(invite)}."
                ),
                button=("Открыть", panel_url(STAGE_PATH[stage])),
            )
        )
        invited += 1

    _log_result(request, stage, to_author=to_author, invited=invited)


def _log_result(request, stage: str, *, to_author: bool, invited: int) -> None:
    """Строка в лог о каждой попытке уведомить.

    Успешную отправку раньше не писали вовсе, и на вопрос «почему не
    пришло» ответить было нечем: непонятно, промолчал бот или система
    решила, что писать некому.
    """
    log.info(
        "Telegram по заявке %s (%s): автору — %s, участникам — %s",
        request.number,
        stage,
        "отправлено" if to_author else "чат не привязан",
        invited,
    )
