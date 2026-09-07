"""Зависимости FastAPI.

Здесь НЕ добавлять `from __future__ import annotations`: FastAPI не
разворачивает отложенные аннотации в зависимостях-классах.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.services.reports import current_period


def get_db() -> Iterator[Session]:
    """Сессия на запрос. Откат при исключении, закрытие всегда."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


class Period:
    """Отчётный период. По умолчанию — текущий месяц в поясе компании."""

    def __init__(
        self,
        year: int | None = Query(default=None, ge=2000, le=2100),
        month: int | None = Query(default=None, ge=1, le=12),
    ) -> None:
        default_year, default_month = current_period()
        self.year = year or default_year
        self.month = month or default_month


PeriodDep = Annotated[Period, Depends(Period)]
