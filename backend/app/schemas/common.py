"""Общие схемы: пагинация, справочные значения."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Страница списка. `total` — всего записей по фильтру, а не на странице."""

    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
