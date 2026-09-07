"""Схемы заявок на расходы."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.db.models import EventKind, PaymentMethod, RequestStatus
from app.schemas.common import ORMModel


class ExpenseLineIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1)
    price: Decimal = Field(ge=0, decimal_places=2)


class ExpenseLineOut(ORMModel):
    id: int
    title: str
    quantity: int
    price: Decimal
    total: Decimal


class RequestEventOut(BaseModel):
    kind: EventKind
    text: str
    actor: str
    #: Метка для интерфейса: «ИВАН ПЕТРОВ · 04.09.2026, 18:12».
    meta: str
    created_at: datetime


class PaymentOut(ORMModel):
    amount: Decimal
    method: PaymentMethod
    document: str
    paid_at: datetime


class RequestListItem(BaseModel):
    """Строка таблицы заявок. Дата уже в местном поясе, строкой."""

    id: int
    number: str
    employee_id: int
    employee_name: str
    employee_position: str
    project_id: int
    project_name: str
    amount: Decimal
    status: RequestStatus
    #: Дата подачи в формате 04.09.2026. Для черновика — дата создания.
    date: str


class RequestDetail(RequestListItem):
    employee_email: str | None
    employee_phone: str | None
    employee_limit: Decimal | None
    employee_spent: Decimal
    lines: list[ExpenseLineOut]
    events: list[RequestEventOut]
    payment: PaymentOut | None
    decision_comment: str | None
    decided_by: str | None


class RequestCreate(BaseModel):
    employee_id: int
    project_id: int
    lines: list[ExpenseLineIn] = Field(min_length=1)
    #: true — сразу отправить на согласование, false — оставить черновиком.
    submit: bool = True


class RequestUpdate(BaseModel):
    """Правка возможна только у черновика."""

    project_id: int | None = None
    lines: list[ExpenseLineIn] | None = Field(default=None, min_length=1)


class DecisionIn(BaseModel):
    """Решение по заявке. При отклонении комментарий обязателен."""

    approve: bool
    comment: str | None = None
    #: Кто принял решение. До входа (фаза 3) передаётся клиентом.
    actor: str | None = None

    @model_validator(mode="after")
    def comment_required_on_reject(self) -> DecisionIn:
        if not self.approve and not (self.comment or "").strip():
            raise ValueError("Комментарий обязателен при отклонении заявки")
        return self


class PaymentIn(BaseModel):
    method: PaymentMethod
    document: str = Field(min_length=1, max_length=64)
    paid_at: datetime | None = None
    actor: str | None = None
