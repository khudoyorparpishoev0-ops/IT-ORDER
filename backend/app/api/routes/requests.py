"""Заявки на расходы.

Видимость: сотрудник без права VIEW_ALL_REQUESTS видит и открывает только
свои заявки. Фильтр по автору навязывается сервером, а не приходит от
клиента, — иначе его достаточно было бы подменить в адресной строке.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from app.api.deps import (
    CurrentUser,
    DbSession,
    PeriodDep,
    RequirePermission,
    bind_audit_actor,
)
from app.core.permissions import Permission, has_permission
from app.db.models import Employee, ExpenseRequest, RequestStatus
from app.schemas.common import Page
from app.schemas.report import Overview
from app.schemas.request import (
    DecisionIn,
    ExpenseLineOut,
    PaymentIn,
    PaymentOut,
    RequestCreate,
    RequestDetail,
    RequestEventOut,
    RequestListItem,
    RequestUpdate,
    SourcingIn,
)
from app.services import reports as reports_svc
from app.services import requests as svc
from app.services.notifications import notify_new_request

router = APIRouter(
    prefix="/api/requests", tags=["requests"], dependencies=[Depends(bind_audit_actor)]
)

can_decide = Depends(RequirePermission(Permission.DECIDE_REQUEST))
can_pay = Depends(RequirePermission(Permission.PAY_REQUEST))
can_source = Depends(RequirePermission(Permission.SOURCE_REQUEST))


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Недостаточно прав для этого действия",
    )


def _visible_employee_id(user: Employee, requested: int | None) -> int | None:
    """Чьи заявки показывать. Без права видеть чужие — только свои."""
    if has_permission(user.role, Permission.VIEW_ALL_REQUESTS):
        return requested
    return user.id


def _ensure_can_view(user: Employee, request: ExpenseRequest) -> None:
    if has_permission(user.role, Permission.VIEW_ALL_REQUESTS):
        return
    if request.employee_id != user.id:
        # 404, а не 403: чужой номер заявки не должен подтверждаться ответом.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена"
        )


def to_list_item(request: ExpenseRequest) -> RequestListItem:
    return RequestListItem(
        id=request.id,
        number=request.number,
        employee_id=request.employee_id,
        employee_name=request.employee.full_name,
        employee_position=request.employee.position,
        project_id=request.project_id,
        project_name=request.project.name,
        title=svc.title_of(request),
        lines_count=len(request.lines),
        amount=request.amount,
        priced=svc.is_priced(request),
        status=request.status,
        awaiting_stage=svc.awaiting_stage(request),
        awaiting_label=svc.awaiting_label(request),
        awaiting_days=svc.awaiting_days(request),
        date=svc.display_date(request),
    )


def to_detail(session, request: ExpenseRequest) -> RequestDetail:
    return RequestDetail(
        **to_list_item(request).model_dump(),
        employee_email=request.employee.email,
        employee_phone=request.employee.phone,
        lines=[ExpenseLineOut.model_validate(line) for line in request.lines],
        events=[
            RequestEventOut(
                kind=e.kind,
                text=e.text,
                actor=e.actor,
                meta=svc.event_meta(e),
                created_at=e.created_at,
            )
            for e in request.events
        ],
        payment=(PaymentOut.model_validate(request.payment) if request.payment else None),
        decision_comment=request.decision_comment,
        decided_by=request.decided_by,
        sourced_by=request.sourced_by,
        sourcing_comment=request.sourcing_comment,
        awaiting_people=svc.awaiting_people(session, request),
    )


@router.get("", response_model=Page[RequestListItem])
def list_requests(
    session: DbSession,
    user: CurrentUser,
    period: PeriodDep,
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    employee_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    all_periods: bool = Query(default=False, description="Игнорировать фильтр по месяцу"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = svc.list_requests(
        session,
        status=status_filter,
        employee_id=_visible_employee_id(user, employee_id),
        project_id=project_id,
        year=None if all_periods else period.year,
        month=None if all_periods else period.month,
        search=search,
        limit=limit,
        offset=offset,
    )
    return Page[RequestListItem](
        items=[to_list_item(r) for r in items], total=total, limit=limit, offset=offset
    )


@router.get("/overview", response_model=Overview)
def overview(session: DbSession, user: CurrentUser, period: PeriodDep):
    """Дашборд. Объявлен раньше `/{request_id}`, иначе слово «overview»
    разобралось бы как номер заявки."""
    data = reports_svc.overview(
        session,
        year=period.year,
        month=period.month,
        employee_id=_visible_employee_id(user, None),
    )
    if has_permission(user.role, Permission.DECIDE_REQUEST):
        queue, total, delayed = reports_svc.decision_queue(session, decider_id=user.id)
        data.queue = [to_list_item(r) for r in queue]
        data.decisions = total
        data.delayed_decisions = delayed
    return data


@router.get("/{request_id}", response_model=RequestDetail)
def get_request(session: DbSession, user: CurrentUser, request_id: int):
    request = svc.get_request(session, request_id, full=True)
    _ensure_can_view(user, request)
    return to_detail(session, request)


@router.post("", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def create_request(
    session: DbSession,
    user: CurrentUser,
    data: RequestCreate,
    background: BackgroundTasks,
):
    """Заявку подают от своего имени. От чужого — только с отдельным правом."""
    if data.employee_id != user.id and not has_permission(
        user.role, Permission.CREATE_REQUEST_FOR_OTHERS
    ):
        raise _forbidden()

    request = svc.create_request(session, data)
    session.flush()
    request = svc.get_request(session, request.id, full=True)
    detail = to_detail(session, request)

    # Письмо согласующим — после ответа клиенту: SMTP занимает секунды,
    # а автор не должен ждать почтовый сервер.
    if request.status is RequestStatus.PENDING:
        background.add_task(_notify_later, request.id)
    background.add_task(_notify_telegram_later, request.id)
    return detail


def _in_own_session(job, request_id: int) -> None:
    """Фоновая отправка идёт в собственной сессии: сессия запроса
    к этому моменту уже закрыта."""
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        job(session, request_id)
    finally:
        session.close()


def _notify_sourcing_later(request_id: int) -> None:
    from app.services.notifications import notify_sourcing

    _in_own_session(notify_sourcing, request_id)


def _notify_priced_later(request_id: int) -> None:
    from app.services.notifications import notify_priced

    _in_own_session(notify_priced, request_id)


def _notify_telegram_later(request_id: int) -> None:
    """Автору — что стало с заявкой, следующему — что она пришла к нему.

    Telegram и push на телефон идут вместе: это одно и то же сообщение
    в два канала, и вызывающему незачем помнить про оба.
    """
    from app.services.push_notify import notify_request_state as push_state
    from app.services.telegram_notify import notify_request_state

    _in_own_session(notify_request_state, request_id)
    _in_own_session(push_state, request_id)


def _notify_later(request_id: int) -> None:
    """Отправка в фоне идёт в собственной сессии: сессия запроса
    к этому моменту уже закрыта."""
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        notify_new_request(session, request_id)
    finally:
        session.close()


@router.patch("/{request_id}", response_model=RequestDetail)
def update_request(
    session: DbSession, user: CurrentUser, request_id: int, data: RequestUpdate
):
    request = svc.get_request(session, request_id, full=True)
    _ensure_can_view(user, request)
    if request.employee_id != user.id and not has_permission(
        user.role, Permission.CREATE_REQUEST_FOR_OTHERS
    ):
        raise _forbidden()

    svc.update_request(session, request_id, data)
    session.flush()
    return to_detail(session, request)


@router.post("/{request_id}/submit", response_model=RequestDetail)
def submit_request(
    session: DbSession, user: CurrentUser, request_id: int, background: BackgroundTasks
):
    request = svc.get_request(session, request_id, full=True)
    _ensure_can_view(user, request)
    if request.employee_id != user.id and not has_permission(
        user.role, Permission.CREATE_REQUEST_FOR_OTHERS
    ):
        raise _forbidden()

    svc.submit_request(session, request, actor=user.full_name)
    detail = to_detail(session, request)
    if request.status is RequestStatus.PENDING:
        background.add_task(_notify_later, request.id)
    background.add_task(_notify_telegram_later, request.id)
    return detail


@router.post(
    "/{request_id}/decision", response_model=RequestDetail, dependencies=[can_decide]
)
def decide_request(
    session: DbSession,
    user: CurrentUser,
    request_id: int,
    data: DecisionIn,
    background: BackgroundTasks,
):
    """Решение по заявке. Имя согласующего берётся из сессии, а не от клиента."""
    request = svc.get_request(session, request_id)
    if request.employee_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя согласовать собственную заявку",
        )
    decision = data.model_copy(update={"actor": user.full_name})
    result = svc.decide_request(session, request_id, decision)
    detail = to_detail(session, result)
    # Согласована покупка — предупреждаем закуп, что заявка у них.
    if result.status is RequestStatus.SOURCING:
        background.add_task(_notify_sourcing_later, result.id)
    background.add_task(_notify_telegram_later, result.id)
    return detail


@router.post(
    "/{request_id}/sourcing", response_model=RequestDetail, dependencies=[can_source]
)
def apply_sourcing(
    session: DbSession,
    user: CurrentUser,
    request_id: int,
    data: SourcingIn,
    background: BackgroundTasks,
):
    """Ответ отдела закупа: что есть на складе, а что почём купить.

    Свою заявку не оценивает даже закупщик: цену на собственную покупку
    он назначал бы сам себе.
    """
    request = svc.get_request(session, request_id)
    if request.employee_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя оценивать собственную заявку",
        )
    result = svc.apply_sourcing(session, request_id, data, actor=user.full_name)
    detail = to_detail(session, result)
    if result.status is RequestStatus.PRICED:
        background.add_task(_notify_priced_later, result.id)
    background.add_task(_notify_telegram_later, result.id)
    return detail


@router.post(
    "/{request_id}/payment", response_model=RequestDetail, dependencies=[can_pay]
)
def pay_request(
    session: DbSession,
    user: CurrentUser,
    request_id: int,
    data: PaymentIn,
    background: BackgroundTasks,
):
    """Проведение выплаты.

    Разделение обязанностей: кто одобрил — тот не платит, и собственную
    заявку не оплачивает даже администратор, у которого есть оба права.
    Иначе один человек проводит расход от начала до конца без чужого
    взгляда, и контроль существует только на бумаге.
    """
    request = svc.get_request(session, request_id)
    if request.employee_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя провести выплату по собственной заявке",
        )
    if request.decided_by and request.decided_by == user.full_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Эту заявку одобрили вы. Выплату проводит кто-то другой — "
                "так устроено разделение обязанностей."
            ),
        )
    payment = data.model_copy(update={"actor": user.full_name})
    request = svc.pay_request(session, request_id, payment)
    detail = to_detail(session, request)
    background.add_task(_notify_telegram_later, request_id)
    return detail


@router.delete(
    "/{request_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # response_model=None обязателен: модуль использует отложенные аннотации,
    # и без него FastAPI строит для 204 тело ответа и падает при старте.
    response_model=None,
    response_class=Response,
)
def delete_request(session: DbSession, user: CurrentUser, request_id: int) -> None:
    request = svc.get_request(session, request_id)
    _ensure_can_view(user, request)
    if request.employee_id != user.id and not has_permission(
        user.role, Permission.CREATE_REQUEST_FOR_OTHERS
    ):
        raise _forbidden()
    svc.delete_request(session, request_id)
