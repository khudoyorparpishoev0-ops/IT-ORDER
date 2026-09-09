"""Push-уведомления на телефон о судьбе заявки.

Тот же смысл, что у Telegram (`telegram_notify.py`): автор узнаёт о каждом
шаге, тот, к кому заявка пришла, — что она у него. Отличие в адресате:
не чат, а подписка браузера, и подписок у человека может быть несколько
(телефон и компьютер). Мёртвые подписки удаляются по ответу push-службы.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ValidationError
from app.core.money import money
from app.core.push import Notification, send_quietly
from app.core.time import utcnow
from app.db.models import Employee, ExpenseRequest, PushSubscription, RequestStatus
from app.schemas.push import PushSubscribeIn
from app.services.audit import write_audit

log = logging.getLogger(__name__)

#: Что сказать автору. Ключ — новый статус заявки.
AUTHOR_TEXT: dict[RequestStatus, str] = {
    RequestStatus.PENDING: "отправлена на согласование покупки",
    RequestStatus.SOURCING: "согласована, передана в отдел закупа",
    RequestStatus.PRICED: "оценена закупом, сумма ушла на утверждение",
    RequestStatus.APPROVED: "утверждена, передана в бухгалтерию",
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


# --- Подписки ----------------------------------------------------------------


def subscribe(session: Session, employee: Employee, data: PushSubscribeIn) -> PushSubscription:
    """Запоминает подписку браузера.

    Endpoint уникален: если тот же браузер подписался под другой учётной
    записью, подписка переезжает к новому человеку — иначе уведомления о
    чужих заявках приходили бы на чужой телефон.
    """
    from app.config import get_settings

    if not get_settings().push_enabled:
        raise ValidationError(
            "Push не настроен: администратор сервера должен задать VAPID_PRIVATE_KEY"
        )

    existing = session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == data.endpoint)
    )
    if existing is not None:
        moved = existing.employee_id != employee.id
        existing.employee_id = employee.id
        existing.p256dh = data.keys.p256dh
        existing.auth = data.keys.auth
        existing.user_agent = data.user_agent
        if moved:
            _audit(session, employee, "push_subscribed", data.user_agent)
        session.flush()
        return existing

    subscription = PushSubscription(
        employee_id=employee.id,
        endpoint=data.endpoint,
        p256dh=data.keys.p256dh,
        auth=data.keys.auth,
        user_agent=data.user_agent,
    )
    session.add(subscription)
    _audit(session, employee, "push_subscribed", data.user_agent)
    session.flush()
    log.info("Push-подписка добавлена сотруднику %s", employee.id)
    return subscription


def unsubscribe(session: Session, employee: Employee, endpoint: str) -> bool:
    """Удаляет подписку этого сотрудника. Чужую трогать нельзя."""
    subscription = session.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint,
            PushSubscription.employee_id == employee.id,
        )
    )
    if subscription is None:
        return False
    session.delete(subscription)
    _audit(session, employee, "push_unsubscribed", subscription.user_agent)
    session.flush()
    return True


def devices(session: Session, employee: Employee) -> int:
    return len(
        session.scalars(
            select(PushSubscription.id).where(PushSubscription.employee_id == employee.id)
        ).all()
    )


def _audit(session: Session, employee: Employee, action: str, details: str | None) -> None:
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action=action,
        employee=employee,
        details=(details or "")[:200] or None,
    )


# --- Отправка ---------------------------------------------------------------


def notify_employee(
    session: Session,
    employee: Employee,
    *,
    title: str,
    body: str,
    url: str,
    tag: str | None = None,
) -> int:
    """Шлёт уведомление на все устройства сотрудника.

    Возвращает, на сколько устройств ушло. Мёртвые подписки удаляет тут же:
    push-служба уже сказала, что их нет.
    """
    subscriptions = session.scalars(
        select(PushSubscription).where(PushSubscription.employee_id == employee.id)
    ).all()
    sent = 0
    dead: list[int] = []
    for sub in subscriptions:
        alive = send_quietly(
            Notification(subscription=sub.info(), title=title, body=body, url=url, tag=tag)
        )
        if alive:
            sub.last_used_at = utcnow()
            sent += 1
        else:
            dead.append(sub.id)
    if dead:
        session.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
        log.info("Удалено %s отозванных push-подписок сотрудника %s", len(dead), employee.id)
    session.flush()
    return sent


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
    parts = [request.number, request.project.name]
    if request.status in (RequestStatus.PRICED, RequestStatus.APPROVED, RequestStatus.PAID):
        parts.append(f"{money(request.amount)} сомони")
    return " · ".join(parts)


def notify_request_state(session: Session, request_id: int) -> None:
    """Автору — что стало с заявкой, следующему — что она у него.

    Принимает id, а не объект: вызывается из фоновой задачи, когда сессия
    запроса уже закрыта.
    """
    from app.core.permissions import Permission, has_permission
    from app.services.notifications import request_url
    from app.services.requests import awaiting_stage

    request = _load(session, request_id)
    if request is None:
        return

    author = request.employee
    what = AUTHOR_TEXT.get(request.status)
    to_author = 0
    if author is not None and author.active and what:
        body = f"{_headline(request)}\n{what.capitalize()}."
        if request.status is RequestStatus.REJECTED and request.decision_comment:
            body += f"\nПричина: {request.decision_comment}"
        to_author = notify_employee(
            session,
            author,
            title="Ваша заявка",
            body=body,
            url=request_url(request),
            tag=f"request-{request.id}",
        )

    stage = awaiting_stage(request)
    invite = ACTOR_TEXT.get(stage)
    invited = 0
    if invite:
        permission = {
            "manager": Permission.DECIDE_REQUEST,
            "procurement": Permission.SOURCE_REQUEST,
            "finance": Permission.PAY_REQUEST,
        }[stage]
        recipients = session.scalars(
            select(Employee)
            .join(PushSubscription, PushSubscription.employee_id == Employee.id)
            .where(Employee.active.is_(True), Employee.notify_new_requests.is_(True))
            .distinct()
        ).all()
        for person in recipients:
            if person.id == request.employee_id:
                continue
            if not has_permission(person.role, permission):
                continue
            invited += notify_employee(
                session,
                person,
                title=f"Заявка {request.number}",
                body=f"{request.employee.full_name} — {invite}.\n{_headline(request)}",
                url=request_url(request),
                tag=f"request-{request.id}",
            )

    log.info(
        "Push по заявке %s (%s): автору — %s устройств, участникам — %s",
        request.number,
        stage,
        to_author,
        invited,
    )
