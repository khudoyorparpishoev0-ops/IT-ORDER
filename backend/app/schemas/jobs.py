"""Схемы фоновых задач."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobRunOut(BaseModel):
    """Запуск задачи — строка в списке «Фоновые задачи»."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job: str
    #: Понятное название задачи для панели.
    label: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    details: str | None


class JobRunResult(BaseModel):
    """Итог ручного запуска."""

    job: str
    label: str
    details: str
