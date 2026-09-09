"""Сводки и отчёты. Только чтение, ничего не меняет."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.money import to_decimal
from app.core.text import count_with_word, days
from app.core.time import format_local_date, local_date, month_bounds, utcnow
from app.db.models import (
    Employee,
    ExpenseRequest,
    MonthlyBudget,
    Payment,
    Project,
    RequestStatus,
)
from app.schemas.report import (
    ApprovalQueueInfo,
    BudgetInfo,
    DashboardStats,
    MonthFact,
    Overview,
    OverviewStage,
    PaidRecord,
    PaymentsRegister,
    ProjectShare,
)
from app.schemas.reference import TeamMemberOut
from app.services.requests import (
    DELAY_DAYS,
    IN_WORK_STATUSES,
    SPENT_STATUSES,
    awaiting_days,
    pending_age_days,
)

MONTH_LABELS = (
    "ЯНВ", "ФЕВ", "МАР", "АПР", "МАЙ", "ИЮН",
    "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК",
)


def _sum_where(session: Session, *conditions) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(ExpenseRequest.amount), 0)).where(*conditions)
    )
    return to_decimal(total or 0)


def _count_where(session: Session, *conditions) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(ExpenseRequest).where(*conditions)
        )
        or 0
    )


def current_period() -> tuple[int, int]:
    """Текущий месяц в местном поясе."""
    today = local_date(utcnow())
    return today.year, today.month


def get_budget(session: Session, year: int, month: int) -> MonthlyBudget | None:
    return session.scalar(
        select(MonthlyBudget).where(
            MonthlyBudget.year == year, MonthlyBudget.month == month
        )
    )


def dashboard_stats(session: Session, *, year: int, month: int) -> DashboardStats:
    start, end = month_bounds(year, month)
    period = (ExpenseRequest.created_at >= start, ExpenseRequest.created_at < end)

    approved_amount = _sum_where(
        session, ExpenseRequest.status == RequestStatus.APPROVED, *period
    )
    # «Ждёт решения» в деньгах — только оценённые заявки: у тех, что ещё
    # не были в закупе, суммы нет вовсе, и складывать там нечего.
    pending_amount = _sum_where(
        session, ExpenseRequest.status == RequestStatus.PRICED, *period
    )
    spent = _sum_where(session, ExpenseRequest.status.in_(SPENT_STATUSES), *period)

    budget = get_budget(session, year, month)
    budget_amount = budget.amount if budget else None
    used_pct = None
    if budget_amount and budget_amount > 0:
        used_pct = int((spent / budget_amount * 100).to_integral_value())

    employees_count = (
        session.scalar(
            select(func.count(func.distinct(ExpenseRequest.employee_id))).where(*period)
        )
        or 0
    )

    return DashboardStats(
        total_requests=_count_where(session, *period),
        employees_count=employees_count,
        approved_amount=approved_amount,
        approved_count=_count_where(
            session, ExpenseRequest.status == RequestStatus.APPROVED, *period
        ),
        pending_amount=pending_amount,
        # А по счётчику — всё, что лежит у руководителя: и согласование
        # покупки, и утверждение суммы.
        pending_count=_count_where(
            session,
            ExpenseRequest.status.in_(
                (RequestStatus.PENDING, RequestStatus.PRICED)
            ),
            *period,
        ),
        budget_amount=budget_amount,
        budget_used_pct=used_pct,
    )


def approval_queue(session: Session) -> ApprovalQueueInfo:
    """Данные баннера: сколько ждёт решения и самая давняя заявка."""
    pending = list(
        session.scalars(
            select(ExpenseRequest)
            .options(selectinload(ExpenseRequest.employee))
            .where(ExpenseRequest.status == RequestStatus.PENDING)
            .order_by(ExpenseRequest.submitted_at.asc().nulls_last())
        )
    )
    priced = _count_where(session, ExpenseRequest.status == RequestStatus.PRICED)
    if not pending:
        return ApprovalQueueInfo(
            count=0, oldest_employee=None, oldest_days=None, priced_count=priced
        )
    oldest = pending[0]
    return ApprovalQueueInfo(
        count=len(pending),
        oldest_employee=oldest.employee.full_name,
        oldest_days=pending_age_days(oldest),
        priced_count=priced,
    )


#: Этапы дашборда «Где стоят заявки» в порядке пути.
OVERVIEW_STAGES: tuple[tuple[RequestStatus, str, str], ...] = (
    (RequestStatus.DRAFT, "draft", "Черновик"),
    (RequestStatus.PENDING, "pending", "Согласование покупки"),
    (RequestStatus.SOURCING, "sourcing", "У закупа"),
    (RequestStatus.PRICED, "priced", "Согласование суммы"),
    (RequestStatus.APPROVED, "approved", "К оплате"),
)


def decision_queue(
    session: Session, *, decider_id: int, limit: int = 3
) -> tuple[list[ExpenseRequest], int, int]:
    """Очередь решений для дашборда: самые давние первыми.

    Собственные заявки не считаются — их этот человек решить не может,
    и кнопка «Согласовать» под ними была бы обманом. Возвращает срез,
    общее число и число задержавшихся.
    """
    rows = list(
        session.scalars(
            select(ExpenseRequest)
            .options(
                selectinload(ExpenseRequest.employee),
                selectinload(ExpenseRequest.project),
                selectinload(ExpenseRequest.lines),
            )
            .where(
                ExpenseRequest.status.in_((RequestStatus.PENDING, RequestStatus.PRICED)),
                ExpenseRequest.employee_id != decider_id,
            )
        )
    )
    now = utcnow()
    rows.sort(key=lambda r: awaiting_days(r, now=now) or 0, reverse=True)
    delayed = sum(1 for r in rows if (awaiting_days(r, now=now) or 0) >= DELAY_DAYS)
    return rows[:limit], len(rows), delayed


def overview(
    session: Session,
    *,
    year: int,
    month: int,
    employee_id: int | None = None,
) -> Overview:
    """Дашборд без очереди: очередь заполняет роутер, у него есть право.

    `employee_id` сужает всё до заявок одного человека — так сотрудник
    видит свой дашборд, а не цифры компании.
    """
    start, end = month_bounds(year, month)
    scope = [] if employee_id is None else [ExpenseRequest.employee_id == employee_id]
    now = utcnow()

    in_work = list(
        session.scalars(
            select(ExpenseRequest).where(
                ExpenseRequest.status.in_(IN_WORK_STATUSES), *scope
            )
        )
    )
    stages: list[OverviewStage] = []
    for status, key, label in OVERVIEW_STAGES:
        waits = [awaiting_days(r, now=now) or 0 for r in in_work if r.status is status]
        stages.append(
            OverviewStage(
                key=key,
                label=label,
                count=len(waits),
                delayed=any(w >= DELAY_DAYS for w in waits),
                avg_days=round(sum(waits) / len(waits), 1) if waits else None,
            )
        )
    busy = [s for s in stages if s.avg_days is not None]
    slowest = max(busy, key=lambda s: s.avg_days or 0) if busy else None
    delayed_total = sum(
        1 for r in in_work if (awaiting_days(r, now=now) or 0) >= DELAY_DAYS
    )

    paid_period = (
        ExpenseRequest.status == RequestStatus.PAID,
        ExpenseRequest.paid_at >= start,
        ExpenseRequest.paid_at < end,
        *scope,
    )
    paid = list(session.scalars(select(ExpenseRequest).where(*paid_period)))
    cycles = [
        (r.paid_at - r.submitted_at).total_seconds() / 86400
        for r in paid
        if r.paid_at is not None and r.submitted_at is not None
    ]

    return Overview(
        decisions=0,
        delayed_decisions=0,
        queue=[],
        in_work=len(in_work),
        delayed_total=delayed_total,
        stages=stages,
        slowest_stage=slowest.label if slowest else None,
        slowest_days=slowest.avg_days if slowest else None,
        to_pay_amount=_sum_where(
            session, ExpenseRequest.status == RequestStatus.APPROVED, *scope
        ),
        to_pay_count=sum(1 for r in in_work if r.status is RequestStatus.APPROVED),
        paid_amount=to_decimal(sum((r.amount for r in paid), Decimal("0"))),
        paid_count=len(paid),
        avg_cycle_days=round(sum(cycles) / len(cycles), 1) if cycles else None,
        rejected_count=_count_where(
            session,
            ExpenseRequest.status == RequestStatus.REJECTED,
            ExpenseRequest.decided_at >= start,
            ExpenseRequest.decided_at < end,
            *scope,
        ),
    )


def shares_by_project(session: Session, *, year: int, month: int) -> list[ProjectShare]:
    """Доли расходов по объектам. Проценты нормализованы до 100."""
    start, end = month_bounds(year, month)
    rows = session.execute(
        select(
            Project.id,
            Project.name,
            func.coalesce(func.sum(ExpenseRequest.amount), 0).label("total"),
        )
        .join(ExpenseRequest, ExpenseRequest.project_id == Project.id)
        .where(
            ExpenseRequest.status.in_(SPENT_STATUSES),
            ExpenseRequest.created_at >= start,
            ExpenseRequest.created_at < end,
        )
        .group_by(Project.id, Project.name)
        .order_by(func.sum(ExpenseRequest.amount).desc())
    ).all()

    total = sum((to_decimal(r.total) for r in rows), Decimal("0.00"))
    if total <= 0:
        return []

    shares = [
        ProjectShare(
            project_id=r.id,
            name=r.name,
            amount=to_decimal(r.total),
            pct=int((to_decimal(r.total) / total * 100).to_integral_value()),
        )
        for r in rows
    ]
    # Округление вниз по каждой строке может недобрать до 100 — разницу
    # отдаём наибольшей доле, иначе полосы визуально не сходятся.
    drift = 100 - sum(s.pct for s in shares)
    if drift and shares:
        shares[0].pct += drift
    return shares


def monthly_facts(session: Session, *, months: int = 6) -> list[MonthFact]:
    """Факт расходов по месяцам, в тысячах сомони. Ось идёт от нуля."""
    year, month = current_period()
    periods: list[tuple[int, int]] = []
    y, m = year, month
    for _ in range(months):
        periods.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    periods.reverse()

    facts: list[MonthFact] = []
    for py, pm in periods:
        start, end = month_bounds(py, pm)
        total = _sum_where(
            session,
            ExpenseRequest.status.in_(SPENT_STATUSES),
            ExpenseRequest.created_at >= start,
            ExpenseRequest.created_at < end,
        )
        facts.append(
            MonthFact(
                year=py,
                month=pm,
                label=MONTH_LABELS[pm - 1],
                value=int((total / 1000).to_integral_value()),
            )
        )
    return facts


def payments_register(
    session: Session, *, year: int, month: int, project_id: int | None = None
) -> PaymentsRegister:
    """Реестр выплат за месяц."""
    start, end = month_bounds(year, month)
    stmt = (
        select(Payment)
        .join(ExpenseRequest, ExpenseRequest.id == Payment.request_id)
        .options(
            selectinload(Payment.request).selectinload(ExpenseRequest.employee),
            selectinload(Payment.request).selectinload(ExpenseRequest.project),
        )
        .where(Payment.paid_at >= start, Payment.paid_at < end)
        .order_by(Payment.paid_at.desc())
    )
    if project_id is not None:
        stmt = stmt.where(ExpenseRequest.project_id == project_id)

    payments = list(session.scalars(stmt))
    items = [
        PaidRecord(
            number=p.request.number,
            employee_name=p.request.employee.full_name,
            project_name=p.request.project.name,
            amount=p.amount,
            method=p.method,
            document=p.document,
            paid_at=format_local_date(p.paid_at),
        )
        for p in payments
    ]
    total = sum((p.amount for p in payments), Decimal("0.00"))

    if payments:
        first = format_local_date(payments[-1].paid_at)
        last = format_local_date(payments[0].paid_at)
        summary = count_with_word(len(payments), "выплата", "выплаты", "выплат")
        summary += f" с {first} по {last}"
        lag = _average_payout_lag(payments)
        if lag is not None:
            summary += f" · средний срок от одобрения до выплаты {days(lag)}"
    else:
        summary = "За период выплат не было"

    return PaymentsRegister(items=items, total=to_decimal(total), summary=summary)


def _average_payout_lag(payments: list[Payment]) -> int | None:
    """Средний срок от одобрения до выплаты, в днях.

    Дата платёжного документа может оказаться раньше даты решения: выплату
    проводят задним числом. Отрицательный срок в отчёте выглядит ошибкой,
    поэтому такие записи считаем нулевыми, а не вычитаем из среднего.
    """
    lags = [
        max(0, (p.paid_at - p.request.decided_at).days)
        for p in payments
        if p.request.decided_at is not None
    ]
    if not lags:
        return None
    return round(sum(lags) / len(lags))


def team_overview(session: Session, *, year: int, month: int) -> list[TeamMemberOut]:
    """Раздел «Команда»: лимит, расход за месяц, доля, число заявок."""
    start, end = month_bounds(year, month)
    rows = session.execute(
        select(
            Employee,
            func.coalesce(
                func.sum(ExpenseRequest.amount).filter(
                    ExpenseRequest.status.in_(SPENT_STATUSES)
                ),
                0,
            ).label("spent"),
            func.count(ExpenseRequest.id).label("cnt"),
        )
        .outerjoin(
            ExpenseRequest,
            (ExpenseRequest.employee_id == Employee.id)
            & (ExpenseRequest.created_at >= start)
            & (ExpenseRequest.created_at < end),
        )
        .where(Employee.active.is_(True))
        .group_by(Employee.id)
        .order_by(Employee.full_name)
    ).all()

    result: list[TeamMemberOut] = []
    for employee, spent, cnt in rows:
        result.append(
            TeamMemberOut(
                id=employee.id,
                full_name=employee.full_name,
                position=employee.position,
                spent=to_decimal(spent or 0),
                requests_count=cnt,
            )
        )
    return result


def budget_info(session: Session, *, year: int, month: int) -> BudgetInfo:
    """Раздел «Финансы»: бюджет месяца и очередь выплат на неделю."""
    start, end = month_bounds(year, month)
    used = _sum_where(
        session,
        ExpenseRequest.status.in_(SPENT_STATUSES),
        ExpenseRequest.created_at >= start,
        ExpenseRequest.created_at < end,
    )
    budget = get_budget(session, year, month)
    limit = budget.amount if budget else None
    remaining = to_decimal(limit - used) if limit is not None else None
    used_pct = None
    if limit and limit > 0:
        used_pct = int((used / limit * 100).to_integral_value())

    # «На этой неделе» — все одобренные и ещё не оплаченные заявки:
    # именно они образуют ближайшую выплату.
    week_amount = _sum_where(session, ExpenseRequest.status == RequestStatus.APPROVED)
    week_count = _count_where(session, ExpenseRequest.status == RequestStatus.APPROVED)

    return BudgetInfo(
        month_limit=limit,
        used=used,
        remaining=remaining,
        used_pct=used_pct,
        week_payout=week_amount,
        week_requests=week_count,
    )


def payout_deadline(days: int = 5) -> str:
    """Срок ближайшей выплаты — подпись в карточке «Финансы»."""
    return format_local_date(utcnow() + timedelta(days=days))
