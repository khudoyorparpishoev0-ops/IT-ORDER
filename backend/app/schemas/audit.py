"""Схемы журнала действий."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class AuditEntryOut(ORMModel):
    """Строка журнала. Тексты для человека собирает панель — здесь только
    факты, чтобы по ним можно было фильтровать и выгружать."""

    id: int
    created_at: datetime
    #: Что менялось: employee / project / request / budget.
    entity: str
    #: Номер заявки или id записи справочника.
    entity_id: str
    action: str
    username: str | None
    employee_id: int | None
    ip: str | None
    details: str | None


class AuditActorOut(BaseModel):
    """Кто встречается в журнале — для фильтра по человеку."""

    employee_id: int | None
    username: str
