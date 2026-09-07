"""Заявки на расходы."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, PeriodDep
from app.core.time import local_date, utcnow
from app.db.models import ExpenseRequest, RequestStatus
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

router = APIRouter(prefix="/api/requests", tags=["requests"])


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
        payment=(
            PaymentOut.model_validate(request.payment) if request.payment else None
        ),
        decision_comment=request.decision_comment,
        decided_by=request.decided_by,
    )


@router.get("", response_model=Page[RequestListItem])
def list_requests(
    session: DbSession,
    period: PeriodDep,
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    employee_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    all_periods: bool = Query(
        default=False, description="Игнорировать фильтр по месяцу"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = svc.list_requests(
        session,
        status=status_filter,
        employee_id=employee_id,
        project_id=project_id,
        year=None if all_periods else period.year,
        month=None if all_periods else period.month,
        search=search,
        limit=limit,
        offset=offset,
    )
    return Page[RequestListItem](
        items=[to_list_item(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=RequestDetail)
def get_request(session: DbSession, request_id: int):
    request = svc.get_request(session, request_id, full=True)
    return to_detail(session, request)


@router.post("", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def create_request(session: DbSession, data: RequestCreate):
    request = svc.create_request(session, data)
    session.flush()
    request = svc.get_request(session, request.id, full=True)
    return to_detail(session, request)


@router.patch("/{request_id}", response_model=RequestDetail)
def update_request(session: DbSession, request_id: int, data: RequestUpdate):
    request = svc.update_request(session, request_id, data)
    session.flush()
    return to_detail(session, request)


@router.post("/{request_id}/submit", response_model=RequestDetail)
def submit_request(session: DbSession, request_id: int, actor: str | None = None):
    request = svc.get_request(session, request_id, full=True)
    svc.submit_request(session, request, actor=actor or request.employee.full_name)
    return to_detail(session, request)


@router.post("/{request_id}/decision", response_model=RequestDetail)
def decide_request(session: DbSession, request_id: int, data: DecisionIn):
    request = svc.decide_request(session, request_id, data)
    return to_detail(session, request)


@router.post("/{request_id}/payment", response_model=RequestDetail)
def pay_request(session: DbSession, request_id: int, data: PaymentIn):
    request = svc.pay_request(session, request_id, data)
    return to_detail(session, request)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT,
    # response_model=None обязателен: модуль использует отложенные аннотации,
    # и без него FastAPI строит для 204 тело ответа и падает при старте.
    response_model=None,
    response_class=Response,
)
def delete_request(session: DbSession, request_id: int) -> None:
    svc.delete_request(session, request_id)
