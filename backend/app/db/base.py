"""Базовый класс моделей и общие типы колонок."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import DateTime, Numeric, String, text
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    """Общий предок моделей."""


#: Деньги: 12 знаков, 2 после запятой. Хватает до 9 999 999 999,99 сомони.
Money = Annotated[Decimal, mapped_column(Numeric(12, 2))]

#: Количество на складе: 14 знаков, 3 после запятой. Кабель метрами,
#: цемент килограммами — целым числом склад не считается. У строки
#: заявки количество по-прежнему целое: её пишет человек словами, а не
#: кладовщик по накладной.
Quantity = Annotated[Decimal, mapped_column(Numeric(14, 3))]

#: Время всегда с таймзоной. PostgreSQL хранит в UTC.
Timestamp = Annotated[datetime, mapped_column(DateTime(timezone=True))]

#: Момент создания записи проставляет база — так он не зависит от часов приложения.
CreatedAt = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False),
]

ShortStr = Annotated[str, mapped_column(String(64))]
Name = Annotated[str, mapped_column(String(200))]
