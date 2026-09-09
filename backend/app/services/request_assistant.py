"""Помощник по заявке: разбирает потребность и доводит её до позиций.

Сотрудник пишет «нужен кабель на камеры Регар» — помощник спрашивает то,
чего не хватает закупу (тип, категория, метраж), и возвращает готовые
строки заявки. Ничего не подставляется молча: позиции применяет человек
кнопкой, отправку заявки помощник не делает.

Контекст формы (объект, автор, уже введённые позиции) уходит в промпт,
чтобы помощник не спрашивал то, что и так видно на экране.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import assistant
from app.schemas.assistant import (
    AssistantContext,
    AssistantLineOut,
    AssistantQuestionOut,
    AssistantReplyOut,
    AssistantTurn,
)
from app.services.assistant_prompt import request_assistant_prompt
from app.services.reference import materials_catalog

log = logging.getLogger(__name__)

#: Сколько реплик диалога отдаём модели. Дальше уточнять уже нечего, а
#: длинная история — лишние деньги за каждый запрос.
MAX_HISTORY = 12


class _Question(BaseModel):
    """Уточняющий вопрос с готовыми вариантами ответа."""

    field: str = Field(description="Короткий английский ключ поля, например cable_type")
    question: str = Field(description="Вопрос сотруднику, одна фраза")
    options: list[str] = Field(description="Готовые варианты ответа; пусто — свободный ответ")


class _Line(BaseModel):
    """Готовая позиция заявки."""

    title: str = Field(description="Наименование с характеристиками")
    quantity: int = Field(description="Количество, целое число не меньше 1")
    unit: str | None = Field(description="Единица: м, шт., бухта, комплект, сутки; или null")
    purpose: str | None = Field(description="Назначение коротко; null — если неизвестно")


class _Reply(BaseModel):
    """Ответ модели. Схема — договор: свободного текста не бывает."""

    status: Literal["need_clarification", "ready", "warning", "recommendation"]
    message: str = Field(description="Одна-две фразы сотруднику")
    questions: list[_Question] = Field(description="До трёх вопросов; пусто при готовой заявке")
    lines: list[_Line] = Field(description="Позиции заявки; пусто, пока данных не хватает")
    warnings: list[str] = Field(description="Сомнения: проверить модель, странное количество")
    recommendations: list[str] = Field(description="Советы, не меняющие заявку")


def _context_block(session: Session, context: AssistantContext) -> str:
    """Что помощник уже знает из формы. Об этом он не спрашивает."""
    lines = [
        f"Сотрудник: {context.employee_name}" if context.employee_name else None,
        f"Объект: {context.project_name}" if context.project_name else "Объект: не выбран",
    ]
    if context.lines:
        rows = [
            f"  - {line.title or 'без названия'}"
            + (f" — {line.quantity}" if line.quantity else "")
            + (f" {line.unit}" if line.unit else "")
            for line in context.lines
        ]
        lines.append("Уже введено в форме:\n" + "\n".join(rows))
    else:
        lines.append("В форме позиций пока нет")

    known = materials_catalog(session, limit=60)
    if known:
        catalog = ", ".join(
            title + (f" ({unit})" if unit else "") for title, unit, _ in known
        )
        lines.append(f"Что уже заказывали раньше: {catalog}")
    return "\n".join(part for part in lines if part)


def _to_out(reply: _Reply) -> AssistantReplyOut:
    return AssistantReplyOut(
        available=True,
        status=reply.status,
        message=reply.message.strip(),
        questions=[
            AssistantQuestionOut(
                field=q.field.strip() or "answer",
                question=q.question.strip(),
                options=[o.strip() for o in q.options if o.strip()][:6],
            )
            for q in reply.questions
            if q.question.strip()
        ][:3],
        lines=[
            AssistantLineOut(
                title=" ".join(line.title.split()),
                quantity=max(1, line.quantity),
                unit=(line.unit or "").strip() or None,
                purpose=(line.purpose or "").strip() or None,
            )
            for line in reply.lines
            if line.title.strip()
        ],
        warnings=[w.strip() for w in reply.warnings if w.strip()][:3],
        recommendations=[r.strip() for r in reply.recommendations if r.strip()][:3],
    )


def converse(
    session: Session,
    *,
    text: str,
    history: list[AssistantTurn],
    context: AssistantContext,
) -> AssistantReplyOut:
    """Одна реплика диалога. Никогда не бросает: сбой модели отдаётся
    признаком `available=false`, и форма работает как раньше."""
    settings = get_settings()
    if not settings.assistant_enabled and assistant._transport is None:
        return AssistantReplyOut(available=False, status="need_clarification", message="")

    question = text.strip()
    if not question and not context.lines:
        return AssistantReplyOut(
            available=True,
            status="need_clarification",
            message="Напишите, что нужно купить или организовать — помогу оформить заявку.",
        )

    prompt = (
        f"Контекст формы:\n{_context_block(session, context)}\n\n"
        f"Сотрудник пишет: «{question}»"
        if question
        else (
            f"Контекст формы:\n{_context_block(session, context)}\n\n"
            "Сотрудник просит проверить заявку по позициям выше: хватает ли "
            "данных закупу, что уточнить."
        )
    )
    turns = [(t.role, t.text.strip()) for t in history[-MAX_HISTORY:] if t.text.strip()]
    try:
        reply = assistant.ask(
            system=request_assistant_prompt(),
            prompt=prompt,
            schema=_Reply,
            history=turns,
            # Разбор потребности требует рассуждения: чем спрашивать, тем
            # и когда данных уже хватает.
            effort="medium",
        )
    except assistant.AssistantError as exc:
        log.warning("Помощник по заявке не ответил: %s", exc)
        return AssistantReplyOut(available=False, status="need_clarification", message="")
    return _to_out(reply)
