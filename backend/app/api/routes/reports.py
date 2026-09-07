"""Сводки, отчёты и финансы."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbSession, PeriodDep
from app.schemas.report import (
    ApprovalQueueInfo,
    BudgetInfo,
    DashboardStats,
    MonthFact,
    PaymentsRegister,
    ProjectShare,
)
from app.services import reports as svc

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(session: DbSession, period: PeriodDep):
    return svc.dashboard_stats(session, year=period.year, month=period.month)


@router.get("/queue", response_model=ApprovalQueueInfo)
def queue(session: DbSession):
    return svc.approval_queue(session)


@router.get("/by-project", response_model=list[ProjectShare])
def by_project(session: DbSession, period: PeriodDep):
    return svc.shares_by_project(session, year=period.year, month=period.month)


@router.get("/monthly", response_model=list[MonthFact])
def monthly(session: DbSession, months: int = Query(default=6, ge=1, le=24)):
    return svc.monthly_facts(session, months=months)


@router.get("/payments", response_model=PaymentsRegister)
def payments(
    session: DbSession, period: PeriodDep, project_id: int | None = Query(default=None)
):
    return svc.payments_register(
        session, year=period.year, month=period.month, project_id=project_id
    )


@router.get("/budget", response_model=BudgetInfo)
def budget(session: DbSession, period: PeriodDep):
    return svc.budget_info(session, year=period.year, month=period.month)
