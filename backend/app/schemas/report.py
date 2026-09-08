"""Схемы отчётов и сводок."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models import PaymentMethod


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
