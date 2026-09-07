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
from app.core.time import local_date, utcnow
from app.db.models import Employee, ExpenseRequest, RequestStatus
from app.schemas.common import Page
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
)
from app.services import requests as svc
from app.services.notifications import notify_new_request

router = APIRouter(
    prefix="/api/requests", tags=["requests"], dependencies=[Depends(bind_audit_actor)]
)

can_decide = Depends(RequirePermission(Permission.DECIDE_REQUEST))
can_pay = Depends(RequirePermission(Permission.PAY_REQUEST))


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
        amount=request.amount,
        status=request.status,
        date=svc.display_date(request),
    )


def to_detail(session, request: ExpenseRequest) -> RequestDetail:
    today = local_date(utcnow())
    spent = svc.spent_by_employee(
        session, request.employee_id, year=today.year, month=today.month
    )
    return RequestDetail(
        **to_list_item(request).model_dump(),
        employee_email=request.employee.email,
        employee_phone=request.employee.phone,
        employee_limit=request.employee.monthly_limit,
        employee_spent=spent,
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
    return detail


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
    return detail


@router.post(
    "/{request_id}/decision", response_model=RequestDetail, dependencies=[can_decide]
)
def decide_request(
    session: DbSession, user: CurrentUser, request_id: int, data: DecisionIn
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
    return to_detail(session, result)


@router.post(
    "/{request_id}/payment", response_model=RequestDetail, dependencies=[can_pay]
)
def pay_request(session: DbSession, user: CurrentUser, request_id: int, data: PaymentIn):
    payment = data.model_copy(update={"actor": user.full_name})
    request = svc.pay_request(session, request_id, payment)
    return to_detail(session, request)


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
