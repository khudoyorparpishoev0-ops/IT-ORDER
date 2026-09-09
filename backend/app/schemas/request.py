"""Схемы заявок на расходы."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.db.models import EventKind, PaymentMethod, RequestStatus
from app.schemas.common import ORMModel


class ExpenseLineIn(BaseModel):
    """Строка заявки от сотрудника: что нужно и сколько.

    Цены здесь нет намеренно — их проставляет отдел закупа после проверки
    склада. Сотрудник описывает потребность, а не смету.
    """

    title: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1)
    #: «шт.», «мешок», «м²» — словами, справочника единиц нет.
    unit: str | None = Field(default=None, max_length=32)


class ExpenseLineOut(ORMModel):
    id: int
    title: str
    quantity: int
    unit: str | None
    #: NULL — строку ещё не оценил закуп.
    price: Decimal | None
    total: Decimal | None
    #: Нашлось на складе: покупать не нужно, в сумму не входит.
    from_stock: bool


class SourcingLineIn(BaseModel):
    """Решение закупа по одной строке: со склада или почём купить."""

    id: int
    from_stock: bool = False
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)

    @model_validator(mode="after")
    def price_required_unless_from_stock(self) -> "SourcingLineIn":
        if self.from_stock:
            # Цена со склада не нужна: денег по этой строке не будет.
            return self
        if self.price is None:
            raise ValueError(
                "Укажите цену или отметьте, что материал есть на складе"
            )
        return self


class SourcingIn(BaseModel):
    """Ответ отдела закупа по всей заявке."""

    lines: list[SourcingLineIn] = Field(min_length=1)
    comment: str | None = Field(default=None, max_length=2000)


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
    #: Наименование для списка: первая строка сметы (+ «и ещё N»).
    title: str
    lines_count: int
    amount: Decimal
    #: false — заявку ещё не оценил закуп, сумма пока ничего не значит.
    priced: bool
    status: RequestStatus
    #: У кого заявка сейчас: author / manager / procurement / finance / closed.
    awaiting_stage: str
    #: Та же мысль словами: «У отдела закупа: склад и цены».
    awaiting_label: str
    #: Сколько полных суток она лежит на текущем шаге. None — закрыта.
    awaiting_days: int | None
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
    sourced_by: str | None
    sourcing_comment: str | None
    #: Кто именно может сделать следующий шаг. Персональных назначений нет:
    #: заявку берёт любой, у кого есть право.
    awaiting_people: list[str]


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
