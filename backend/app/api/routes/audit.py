"""Журнал действий: кто, что и когда делал в системе.

Только чтение. Записи журнала не правятся и не удаляются — ни через API,
ни через панель: журнал ценен именно тем, что его нельзя переписать.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, RequirePermission, bind_audit_actor
from app.core.permissions import Permission
from app.core.time import local_day_bounds
from app.schemas.audit import AuditActorOut, AuditEntryOut
from app.schemas.common import Page
from app.services import audit as svc

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[
        Depends(RequirePermission(Permission.VIEW_AUDIT)),
        Depends(bind_audit_actor),
    ],
)


def _from(value: date | None) -> datetime | None:
    """Начало местных суток в UTC: в фильтре человек указывает свою дату."""
    return None if value is None else local_day_bounds(value)[0]


def _to(value: date | None) -> datetime | None:
    """Начало следующих суток: «по 7 сентября» включает всё 7-е число."""
    return None if value is None else local_day_bounds(value)[1]


@router.get("", response_model=Page[AuditEntryOut])
def list_entries(
    session: DbSession,
    entity: str | None = Query(default=None),
    action: str | None = Query(default=None),
    employee_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = svc.list_audit(
        session,
        entity=entity,
        action=action,
        employee_id=employee_id,
        search=search,
        date_from=_from(date_from),
        date_to=_to(date_to),
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[AuditEntryOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/actors", response_model=list[AuditActorOut])
def actors(session: DbSession):
    """Кто встречается в журнале — для выпадающего списка фильтра."""
    return [
        AuditActorOut(employee_id=employee_id, username=username)
        for employee_id, username in svc.audit_actors(session)
    ]
