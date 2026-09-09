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
    project_id: int | None = None
    project_name: str | None = Field(default=None, max_length=200)
    #: Кто заполняет форму. Ставит сервер из сессии, не клиент.
    employee_id: int | None = None
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
    #: Номер записи в журнале обращений: по нему панель отмечает, что
    #: позиции перенесли в заявку кнопкой «Применить».
    interaction_id: int | None = None


# --- Память заявок: работает без модели --------------------------------------


class MemoryItem(BaseModel):
    """Подсказка из истории заявок: как это называли и сколько раз брали."""

    title: str
    unit: str | None = None
    times: int
    #: Номер и дата последней заявки с этой позицией: подсказка должна
    #: быть проверяемой, а не появляться ниоткуда.
    last_number: str | None = None
    last_date: str | None = None


class SimilarRequestOut(BaseModel):
    """Недавняя заявка с теми же позициями. Решение — за человеком."""

    id: int
    number: str
    title: str
    project: str
    employee: str
    status: str
    days_ago: int
    materials: list[str] = []


class MemoryOut(BaseModel):
    """Что ORDER помнит о заявках — до всякой модели.

    Все три списка считаются запросами к базе, поэтому подсказки живут и
    при выключенном помощнике: кончился баланс — автодополнение осталось.
    """

    #: Что просят чаще всего (по объекту, если он выбран).
    frequent: list[MemoryItem] = []
    #: Что заказывал сам сотрудник.
    mine: list[MemoryItem] = []
    #: Что заказывали на выбранном объекте.
    project: list[MemoryItem] = []


class DuplicateCheckIn(BaseModel):
    """Проверка на повтор: позиции из формы и объект."""

    titles: list[str] = Field(default_factory=list, max_length=30)
    project_id: int | None = None


class DuplicateCheckOut(BaseModel):
    """Похожие заявки за последнюю неделю."""

    requests: list[SimilarRequestOut] = []
    days: int
