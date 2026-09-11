"""Схемы склада.

Количества приходят и уходят `Decimal` с тремя знаками — как деньги,
только своя точность (`app/core/quantity.py`). Остаток в этих схемах
только читается: эндпоинта, который принимал бы новое значение остатка,
в API нет вовсе. Остаток меняют документы, а не человек с клавиатурой.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models import StockDocKind, StockDocStatus, StockMoveKind
from app.schemas.common import ORMModel

#: Сколько строк принимаем в одном документе. Приход на сотню позиций —
#: это не один документ, а выгрузка, и разбирать её надо иначе.
MAX_LINES = 100


# --------------------------------------------------------------------------
# Места хранения
# --------------------------------------------------------------------------
class WarehouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    #: Объект, на котором стоит склад. NULL — центральный.
    project_id: int | None = None
    address: str | None = Field(default=None, max_length=200)
    #: Материально ответственный.
    keeper_id: int | None = None
    active: bool = True


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: int | None = None
    address: str | None = Field(default=None, max_length=200)
    keeper_id: int | None = None
    active: bool | None = None


class WarehouseOut(ORMModel):
    id: int
    name: str
    project_id: int | None
    project_name: str | None = None
    address: str | None
    keeper_id: int | None
    keeper_name: str | None = None
    active: bool
    #: Сколько позиций лежит на складе и на какую сумму. Сумма приходит
    #: только тем, кому позволено видеть закупочную стоимость.
    items_count: int = 0
    value: Decimal | None = None


# --------------------------------------------------------------------------
# Номенклатура
# --------------------------------------------------------------------------
class StockItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="шт.", min_length=1, max_length=32)
    article: str | None = Field(default=None, max_length=64)
    min_quantity: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=3)
    track_serial: bool = False
    note: str | None = None


class StockItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    article: str | None = Field(default=None, max_length=64)
    min_quantity: Decimal | None = Field(default=None, ge=0, decimal_places=3)
    track_serial: bool | None = None
    active: bool | None = None
    note: str | None = None


class StockItemOut(ORMModel):
    id: int
    name: str
    unit: str
    article: str | None
    min_quantity: Decimal
    track_serial: bool
    active: bool
    note: str | None
    #: Остаток по всем складам сразу. Разбивка — в карточке позиции.
    quantity: Decimal = Decimal("0")
    #: Остаток ниже минимального и он задан: позиция заканчивается.
    low: bool = False


class BalanceOut(BaseModel):
    """Остаток по паре «склад + позиция». Только для чтения."""

    warehouse_id: int
    warehouse_name: str
    item_id: int
    item_name: str
    unit: str
    quantity: Decimal
    low: bool = False


class ItemCardOut(BaseModel):
    """Карточка позиции: где лежит и что с ней происходило."""

    item: StockItemOut
    balances: list[BalanceOut]
    moves: list["MoveOut"]


# --------------------------------------------------------------------------
# Документы
# --------------------------------------------------------------------------
class DocumentLineIn(BaseModel):
    """Строка документа.

    Позиция задаётся либо ссылкой (`item_id`), либо названием (`title`) —
    тогда она заводится на лету: кладовщик принимает товар, а не ведёт
    справочник. Цена нужна только приходу.
    """

    item_id: int | None = None
    title: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=32)
    quantity: Decimal = Field(gt=0, decimal_places=3)
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    comment: str | None = Field(default=None, max_length=200)


class ReceiptIn(BaseModel):
    """Приход: привезли на склад."""

    warehouse_id: int
    supplier: str | None = Field(default=None, max_length=200)
    comment: str | None = None
    lines: list[DocumentLineIn] = Field(min_length=1, max_length=MAX_LINES)


class IssueIn(BaseModel):
    """Выдача: со склада человеку на объект."""

    warehouse_id: int
    #: Кому выдали. Обязателен: выдача «никому» ничего не объясняет.
    recipient_id: int
    #: На какой объект ушло.
    project_id: int | None = None
    comment: str | None = None
    lines: list[DocumentLineIn] = Field(min_length=1, max_length=MAX_LINES)


class ReturnIn(BaseModel):
    """Возврат: не пригодилось, вернули на склад."""

    warehouse_id: int
    #: Кто вернул.
    recipient_id: int
    project_id: int | None = None
    comment: str | None = None
    lines: list[DocumentLineIn] = Field(min_length=1, max_length=MAX_LINES)


class CancelIn(BaseModel):
    """Отмена документа. Причина обязательна: отмена без объяснения — это
    та же правка задним числом, только через другую кнопку."""

    reason: str = Field(min_length=3, max_length=500)


class DocumentLineOut(ORMModel):
    id: int
    item_id: int
    item_name: str = ""
    unit: str = ""
    quantity: Decimal
    price: Decimal | None
    total: Decimal | None
    comment: str | None


class DocumentOut(ORMModel):
    id: int
    number: str
    kind: StockDocKind
    status: StockDocStatus
    warehouse_id: int
    warehouse_name: str = ""
    created_by: str | None
    recipient_name: str | None = None
    project_name: str | None = None
    supplier: str | None
    comment: str | None
    total: Decimal | None
    lines_count: int = 0
    created_at: datetime
    cancelled_at: datetime | None = None
    cancelled_by: str | None = None
    cancel_reason: str | None = None


class DocumentDetailOut(DocumentOut):
    lines: list[DocumentLineOut] = []


class MoveOut(BaseModel):
    """Движение ленты. Количество со знаком: «+» пришло, «−» ушло."""

    id: int
    document_id: int
    document_number: str
    kind: StockMoveKind
    warehouse_id: int
    warehouse_name: str
    item_id: int
    item_name: str
    unit: str
    quantity: Decimal
    price: Decimal | None = None
    actor: str | None = None
    created_at: datetime


class StockOverviewOut(BaseModel):
    """Что показывать на первом экране склада."""

    warehouses: int
    items: int
    #: Позиций с остатком ниже минимального.
    low_items: int
    #: Оценка запаса. NULL — нет права видеть закупочную стоимость.
    value: Decimal | None = None
    moves_today: int


ItemCardOut.model_rebuild()
