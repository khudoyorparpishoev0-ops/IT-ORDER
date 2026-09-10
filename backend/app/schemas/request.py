"""Схемы заявок на расходы."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.db.models import EventKind, PaymentMethod, RequestCategory, RequestStatus
from app.schemas.common import ORMModel


class ExpenseLineIn(BaseModel):
    """Строка заявки от сотрудника: что нужно и сколько.

    Цены здесь нет намеренно — их проставляет отдел закупа после проверки
    склада. Сотрудник описывает потребность, а не смету.
    """

    title: str = Field(min_length=1, max_length=200)
    #: Что человек набрал своими руками, до правки помощником. Пусто —
    #: он ничего не набирал (шаблон, повтор, позиция от помощника), тогда
    #: исходным считается итоговое название.
    original_text: str | None = Field(default=None, max_length=200)
    quantity: int = Field(ge=1)
    #: «шт.», «мешок», «м²» — словами, справочника единиц нет.
    unit: str | None = Field(default=None, max_length=32)


class ExpenseLineOut(ORMModel):
    id: int
    title: str
    #: Что набрал человек до правки. Совпадает с `title`, если он ничего
    #: не менял или если строка старше миграции 0016.
    original_text: str = ""
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
    #: Кто это сделал: `human` — человек, `system` — переход как следствие
    #: чужого решения. Подписывать такой переход именем значит утверждать,
    #: что человек сделал два действия вместо одного.
    actor_type: str = "human"
    #: Подробности: «было → стало» по статусу и сумме, состав правки,
    #: у кого заявка теперь. Пусто у событий до появления истории.
    details: dict = Field(default_factory=dict)
    created_at: datetime


class RequestViewerOut(BaseModel):
    """Кто открывал заявку. IP и user-agent сюда не попадают: обычному
    сотруднику они ничего не объясняют, а хранить и показывать их «на
    всякий случай» — это следить за людьми, а не вести историю."""

    employee_id: int
    employee_name: str
    #: Дата и время в местном поясе, строкой: «04.09.2026, 18:12».
    first_viewed_at: str
    last_viewed_at: str
    #: Сколько раз открывал. Возвращения в пределах получаса — один раз.
    times: int


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
    #: Бизнес-категория расхода. None — не указана.
    category: RequestCategory | None = None
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
    #: Кто открывал карточку. Автору видно, дошла ли заявка до глаз, а не
    #: только до очереди.
    viewers: list[RequestViewerOut] = Field(default_factory=list)


class RequestCreate(BaseModel):
    employee_id: int
    project_id: int
    lines: list[ExpenseLineIn] = Field(min_length=1)
    #: Бизнес-категория. Помощник предлагает, человек подтверждает; None —
    #: не указана, и это честнее, чем свалить заявку в «Другое».
    category: RequestCategory | None = None
    #: true — сразу отправить на согласование, false — оставить черновиком.
    submit: bool = True


class RequestUpdate(BaseModel):
    """Правка возможна только у черновика."""

    project_id: int | None = None
    category: RequestCategory | None = None
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
