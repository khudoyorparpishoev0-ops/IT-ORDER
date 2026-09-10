"""Схемы шаблонов заявок. Зеркалятся в frontend/src/api/types.ts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateLine(BaseModel):
    """Позиция шаблона. Форма та же, что у строки формы заявки."""

    title: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1, le=1_000_000)
    unit: str | None = Field(default=None, max_length=32)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_id: int | None = None
    lines: list[TemplateLine] = Field(min_length=1, max_length=30)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    project_id: int | None = None
    #: true — снять объект. Отличается от `project_id: null`, который в
    #: PATCH значит «не трогать»: без этого признака объект нельзя было
    #: бы убрать, только заменить.
    clear_project: bool = False
    lines: list[TemplateLine] | None = Field(default=None, max_length=30)


class TemplateOut(BaseModel):
    id: int
    name: str
    project_id: int | None
    project_name: str | None
    lines: list[TemplateLine]
    usage_count: int
    last_used_at: str | None


class TemplateApplyOut(BaseModel):
    """Шаблон, готовый к подстановке в форму. Заявку не создаёт."""

    template: TemplateOut
    #: Объект шаблона отключён или удалён — молча подставлять его нельзя.
    warning: str | None = None
