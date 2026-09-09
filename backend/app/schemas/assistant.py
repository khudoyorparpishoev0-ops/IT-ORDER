"""Схемы помощника по заявке. Зеркалятся в frontend/src/api/types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssistantFormLine(BaseModel):
    """Строка, уже введённая в форме. Об этом помощник не спрашивает."""

    title: str = Field(default="", max_length=200)
    quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    unit: str | None = Field(default=None, max_length=32)


class AssistantContext(BaseModel):
    """Что видно на экране у сотрудника прямо сейчас."""

    employee_name: str | None = Field(default=None, max_length=200)
    project_name: str | None = Field(default=None, max_length=200)
    lines: list[AssistantFormLine] = Field(default_factory=list, max_length=30)


class AssistantTurn(BaseModel):
    """Реплика диалога. Историю хранит панель: у помощника памяти нет."""

    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class AssistantAskIn(BaseModel):
    """Вопрос помощнику: текст сотрудника плюс контекст формы."""

    text: str = Field(default="", max_length=2000)
    history: list[AssistantTurn] = Field(default_factory=list, max_length=20)
    context: AssistantContext = Field(default_factory=AssistantContext)


class AssistantQuestionOut(BaseModel):
    """Уточняющий вопрос: варианты рисуются кнопками."""

    field: str
    question: str
    options: list[str] = []


class AssistantLineOut(BaseModel):
    """Позиция, предложенная помощником. Применяет её человек."""

    title: str
    quantity: int
    unit: str | None = None
    #: Назначение: «подключение наружных IP-камер».
    purpose: str | None = None


class AssistantReplyOut(BaseModel):
    """Ответ помощника."""

    #: false — модель недоступна или помощник выключен; панель молчит.
    available: bool
    status: Literal["need_clarification", "ready", "warning", "recommendation"]
    message: str
    questions: list[AssistantQuestionOut] = []
    lines: list[AssistantLineOut] = []
    warnings: list[str] = []
    recommendations: list[str] = []
