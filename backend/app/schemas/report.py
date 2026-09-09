"""Схемы отчётов и сводок."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models import PaymentMethod
from app.schemas.request import RequestListItem


class DashboardStats(BaseModel):
    """Четыре метрики на панели управления."""

    total_requests: int
    employees_count: int
    approved_amount: Decimal
    approved_count: int
    pending_amount: Decimal
    pending_count: int
    budget_amount: Decimal | None
    budget_used_pct: int | None


class ApprovalQueueInfo(BaseModel):
    """Баннер очереди на панели."""

    #: Сколько заявок ждёт согласования самой покупки.
    count: int
    oldest_employee: str | None
    oldest_days: int | None
    #: Сколько заявок вернулось из закупа и ждёт решения по сумме.
    priced_count: int = 0


class OverviewStage(BaseModel):
    """Один этап пути заявки на дашборде: сколько заявок на нём стоит."""

    key: str
    label: str
    count: int
    #: Хотя бы одна заявка стоит на этапе дольше порога задержки.
    delayed: bool
    #: Среднее ожидание на этапе в сутках, None — этап пуст.
    avg_days: float | None


class Overview(BaseModel):
    """Дашборд: очередь на решение, где стоят заявки, справочные цифры.

    Считается по заявкам, которые видит вошедший: сотрудник — по своим,
    руководитель — по всем.
    """

    #: Сколько решений ждёт именно этого человека (0 — права решать нет).
    decisions: int
    #: Из них дольше порога задержки.
    delayed_decisions: int
    #: До трёх заявок из очереди, самые давние первыми.
    queue: list[RequestListItem]
    #: Заявок в работе (не закрытых) всего.
    in_work: int
    #: Из них стоят на своём шаге дольше порога.
    delayed_total: int
    stages: list[OverviewStage]
    slowest_stage: str | None
    slowest_days: float | None
    to_pay_amount: Decimal
    to_pay_count: int
    paid_amount: Decimal
    paid_count: int
    #: Среднее число суток от подачи до выплаты по выплатам месяца.
    avg_cycle_days: float | None
    rejected_count: int


class ProjectShare(BaseModel):
    project_id: int
    name: str
    amount: Decimal
    pct: int


class MonthFact(BaseModel):
    year: int
    month: int
    label: str
    #: Сумма в тысячах сомони — так подписаны столбцы в макете.
    value: int


class PaidRecord(BaseModel):
    number: str
    employee_name: str
    project_name: str
    amount: Decimal
    method: PaymentMethod
    document: str
    paid_at: str


class PaymentsRegister(BaseModel):
    items: list[PaidRecord]
    total: Decimal
    summary: str


class BudgetIn(BaseModel):
    """Сумма бюджета на месяц. Период — в параметрах запроса."""

    amount: Decimal = Field(ge=0, le=Decimal("9999999999.99"))


class BudgetInfo(BaseModel):
    month_limit: Decimal | None
    used: Decimal
    remaining: Decimal | None
    used_pct: int | None
    week_payout: Decimal
    week_requests: int
