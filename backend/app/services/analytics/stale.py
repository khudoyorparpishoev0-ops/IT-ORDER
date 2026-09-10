"""Заявки без движения: где стоит и сколько уже стоит.

Отличие от норматива этапа. Норматив отвечает «уложились ли»; «без
движения» отвечает «сколько уже не трогали». Заявка может укладываться в
норматив закупа (сутки) и всё равно стоять двадцать три часа — и это то,
что руководитель хочет увидеть до того, как норматив нарушен.

Время считается от входа в текущий шаг (`awaiting_since`), а не от
подачи: заявка, поданная неделю назад и вчера пришедшая в бухгалтерию,
стоит день, а не неделю.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utcnow
from app.db.models import Employee, ExpenseRequest, Project, RequestStatus
from app.services.analytics import sla
from app.services.analytics.scope import Scope
from app.services.requests import awaiting_label, awaiting_since, awaiting_stage, title_of

#: Заявки, по которым чего-то ждут. Оплаченная, отклонённая и закрытая
#: складом уже никого не задерживают.
IN_WORK = (
    RequestStatus.PENDING,
    RequestStatus.SOURCING,
    RequestStatus.PRICED,
    RequestStatus.APPROVED,
)

#: Насколько нужно превысить норматив, чтобы это стало критичным.
CRITICAL_FACTOR = 2


@dataclass(frozen=True)
class Stuck:
    """Заявка, которая стоит дольше положенного."""

    request_id: int
    number: str
    title: str
    project_id: int
    project: str
    employee: str
    status: str
    stage: str
    stage_label: str
    #: Сколько часов стоит на текущем шаге.
    hours_in_status: int
    #: Норматив шага, часов. None — норматива нет.
    norm_hours: int | None
    #: Кто должен её сдвинуть: «Отдел закупа», «Руководитель».
    assignee: str
    #: critical | warning | info
    severity: str
    #: Просрочена по нормативу этапа.
    overdue: bool
    reason: str


def _severity(hours: int, norm: int | None, threshold: int) -> tuple[str, bool]:
    """Насколько всё плохо и просрочена ли по нормативу."""
    if norm is not None and hours >= norm * CRITICAL_FACTOR:
        return "critical", True
    if norm is not None and hours >= norm:
        return "warning", True
    if hours >= threshold:
        return "warning", False
    return "info", False


def in_work(session: Session, *, scope: Scope | None = None) -> list[ExpenseRequest]:
    """Незакрытые заявки со всем, что понадобится разбору.

    Единственная точка, где аналитика берёт заявки: и сводка
    руководителя, и очередь внимания, и нестыковки идут отсюда. Поэтому
    границу видимости достаточно навязать здесь — забыть её в одном из
    разделов невозможно.
    """
    stmt = (
        select(ExpenseRequest)
        .options(
            selectinload(ExpenseRequest.employee),
            selectinload(ExpenseRequest.project),
            selectinload(ExpenseRequest.lines),
        )
        .where(ExpenseRequest.status.in_(IN_WORK))
        .order_by(ExpenseRequest.created_at)
    )
    if scope is not None:
        visible = scope.visible_employee_id
        if visible is not None:
            stmt = stmt.where(ExpenseRequest.employee_id == visible)
        if scope.projects:
            stmt = stmt.where(ExpenseRequest.project_id.in_(scope.projects))
    return list(session.scalars(stmt))


def hours_in_status(request: ExpenseRequest, now: datetime) -> int:
    since = awaiting_since(request) or request.created_at
    return max(0, int((now - since).total_seconds() // 3600))


def stuck_requests(
    session: Session,
    *,
    now: datetime | None = None,
    threshold_hours: int | None = None,
    rows: list[ExpenseRequest] | None = None,
    scope: Scope | None = None,
) -> list[Stuck]:
    """Заявки, которые стоят дольше норматива или дольше порога.

    Порог настраивается (`STALE_HOURS`): у разных компаний разный ритм.
    """
    moment = now or utcnow()
    threshold = threshold_hours if threshold_hours is not None else sla.stale_hours()
    norms = sla.norms()
    result: list[Stuck] = []

    for request in rows if rows is not None else in_work(session, scope=scope):
        hours = hours_in_status(request, moment)
        norm = norms.get(request.status)
        severity, overdue = _severity(hours, norm, threshold)
        if severity == "info":
            continue

        if overdue and norm is not None:
            reason = f"стоит {hours} ч при нормативе {norm} ч"
        else:
            reason = f"без движения {hours} ч"

        result.append(
            Stuck(
                request_id=request.id,
                number=request.number,
                title=title_of(request),
                project_id=request.project_id,
                project=request.project.name,
                employee=request.employee.full_name,
                status=request.status.value,
                stage=awaiting_stage(request),
                stage_label=awaiting_label(request),
                hours_in_status=hours,
                norm_hours=norm,
                assignee=awaiting_label(request),
                severity=severity,
                overdue=overdue,
                reason=reason,
            )
        )

    result.sort(key=lambda s: (s.severity != "critical", -s.hours_in_status))
    return result
