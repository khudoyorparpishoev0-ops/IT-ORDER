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
import time
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import assistant
from app.db.models import AiKind, AiSource
from app.schemas.assistant import (
    AssistantContext,
    AssistantLineOut,
    AssistantQuestionOut,
    AssistantReplyOut,
    AssistantTurn,
)
from app.services import ai_log, ai_memory
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

    # Память ORDER: чем чаще позицию берут на этом объекте, тем вероятнее
    # она нужна и сейчас. Считает базу сервер — модель ничего не выбирает
    # сама и не может назвать материал, которого в компании не заказывали.
    if context.project_id is not None:
        on_site = ai_memory.by_project(session, context.project_id, limit=10)
        if on_site:
            lines.append(
                "Что чаще берут на этом объекте: "
                + ", ".join(
                    f"{x.title} ({x.times})" for x in on_site
                )
            )
    if context.employee_id is not None:
        own = ai_memory.mine(session, context.employee_id, limit=10)
        if own:
            lines.append(
                "Что обычно заказывает этот сотрудник: "
                + ", ".join(x.title for x in own)
            )
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
    source: AiSource = AiSource.WEB,
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
    # В журнал пишем реплику сотрудника, а не весь промпт: каталог и
    # контекст формы он и так видел, а хранить их копию на каждый вопрос —
    # это мегабайты ради ничего.
    asked = question or "проверка формы"
    started = time.monotonic()
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
        ai_log.record(
            session,
            kind=AiKind.REQUEST,
            question=asked,
            ok=False,
            error=str(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
            source=source,
        )
        return AssistantReplyOut(available=False, status="need_clarification", message="")

    out = _to_out(reply)
    entry_id = ai_log.record(
        session,
        kind=AiKind.REQUEST,
        question=asked,
        answer=_answer_text(out),
        duration_ms=int((time.monotonic() - started) * 1000),
        source=source,
    )
    return out.model_copy(update={"interaction_id": entry_id})


def _answer_text(reply: AssistantReplyOut) -> str:
    """Ответ одной строкой для журнала: фраза помощника и что он предложил."""
    parts = [reply.message]
    if reply.questions:
        parts.append("Вопросы: " + "; ".join(q.question for q in reply.questions))
    if reply.lines:
        parts.append(
            "Позиции: "
            + "; ".join(
                f"{line.title} — {line.quantity}" + (f" {line.unit}" if line.unit else "")
                for line in reply.lines
            )
        )
    return "\n".join(part for part in parts if part)
