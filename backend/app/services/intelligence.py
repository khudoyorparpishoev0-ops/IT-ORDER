"""AI-аналитик: объясняет готовые цифры словами.

Модель не ходит в базу и не пишет запросов. Она получает подготовленный
текстовый блок фактов (`app/services/analytics.py`) и вопрос
руководителя, а отвечает по схеме. Такой порядок закрывает две дыры
сразу: модель не может обойти права ролей (данных, которых человеку не
положено видеть, в блоке просто нет) и не может ошибиться в арифметике.

Сбой модели никогда не прячет цифры: сводка показывается и без слов,
поле `ai.available` говорит панели, что текста не будет.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import assistant
from app.db.models import AiKind
from app.core.money import money
from app.schemas.analytics import (
    AnalyticsReplyOut,
    AnalyticsRequestRef,
    AnalyticsTurn,
    AiText,
    DigestOut,
)
from app.services import ai_log
from app.services.analytics import digest_facts
from app.services.analytics_prompt import analytics_prompt

log = logging.getLogger(__name__)

#: Сколько реплик диалога отдаём модели. Дальше — лишние деньги за каждый
#: запрос: аналитика опирается на свежие факты, а не на длинную переписку.
MAX_HISTORY = 10


class _Digest(BaseModel):
    """Слова модели к сводке."""

    headline: str = Field(description="Одна фраза-вывод для руководителя")
    summary: list[str] = Field(description="Что происходит и где проблема, до пяти пунктов")
    recommendations: list[str] = Field(description="Что стоит сделать, до трёх пунктов")


class _Reference(BaseModel):
    number: str = Field(description="Номер заявки из данных, например РЗ-0041")
    why: str = Field(description="Почему её стоит открыть, одна фраза")


class _Answer(BaseModel):
    """Ответ на вопрос руководителя."""

    answer: str = Field(description="Ответ одной-двумя фразами")
    bullets: list[str] = Field(description="Подробности по пунктам, до пяти")
    requests: list[_Reference] = Field(description="Заявки, которые стоит открыть")
    recommendations: list[str] = Field(description="Что сделать, до трёх пунктов")


def _num(value: float | None, unit: str = "") -> str:
    if value is None:
        return "нет данных"
    text = f"{value:.1f}".replace(".0", "").replace(".", ",")
    return f"{text} {unit}".strip()


def facts_block(data: DigestOut) -> str:
    """Готовые цифры для модели. Каждая строка — факт из базы.

    Формат нарочно плоский и короткий: модель должна цитировать числа,
    а не разбирать вложенный JSON.
    """
    t = data.totals
    lines: list[str] = [
        f"Момент: {data.generated_at}",
        "",
        "СЧЁТЧИКИ",
        f"- В работе: {t.active}; черновиков: {t.drafts}",
        f"- Подано: сегодня {t.created_today}, за неделю {t.created_week}, за месяц {t.created_month}",
        f"- Завершено: сегодня {t.done_today}, за месяц {t.done_month}; отклонено за месяц {t.rejected_month}",
        f"- Вышли за норматив этапа: {t.over_norm}",
        f"- Критичных: {t.critical}; требуют внимания: {t.attention}",
        f"- К оплате: {money(t.to_pay_amount)} сомони по {t.to_pay_count} заявкам",
        f"- Оплачено за месяц: {money(t.paid_month_amount)} сомони по {t.paid_month_count} заявкам",
        f"- Средний цикл от подачи до выплаты: {_num(t.avg_cycle_days, 'суток')}",
    ]
    if t.budget_amount is not None:
        lines.append(
            f"- Бюджет месяца: {money(t.budget_amount)} сомони, использовано {t.budget_used_pct}%"
        )
    else:
        lines.append("- Бюджет месяца не задан")

    lines += ["", "ЭТАПЫ (где стоят заявки)"]
    for stage in data.stages:
        norm = f"норма {stage.norm_hours} ч" if stage.norm_hours else "норматива нет"
        lines.append(
            f"- {stage.label}: {stage.count} заявок, ждут в среднем "
            f"{_num(stage.avg_hours, 'ч')}, {norm}, за нормативом {stage.over_norm}; "
            f"фактически этап занимает {_num(stage.done_avg_hours, 'ч')} "
            f"(за прошлый месяц {_num(stage.done_prev_avg_hours, 'ч')})"
        )

    if data.attention:
        lines += ["", "ТРЕБУЮТ ВНИМАНИЯ"]
        for item in data.attention:
            level = {"critical": "критично", "attention": "внимание"}.get(item.level, "норма")
            amount = f"{money(item.amount)} сомони" if item.priced else "не оценена"
            lines.append(
                f"- {item.number} ({level}): {item.title}; объект {item.project}; "
                f"автор {item.employee}; сейчас у: {item.holder}; {item.hours} ч на этапе; "
                f"{amount}; причины: {'; '.join(item.reasons)}"
            )

    if data.in_work:
        lines += ["", "ЗАЯВКИ В РАБОТЕ (номер, наименование, объект, автор, у кого, часов, сумма)"]
        for brief in data.in_work:
            amount = f"{money(brief.amount)} сомони" if brief.priced else "не оценена"
            lines.append(
                f"- {brief.number}; {brief.title}; {brief.project}; {brief.employee}; "
                f"у: {brief.holder}; {brief.hours} ч; {amount}"
            )

    if data.duplicates:
        lines += ["", "ПОХОЖИЕ ЗАЯВКИ (возможные дубликаты)"]
        for pair in data.duplicates:
            lines.append(
                f"- {pair.first_number} и {pair.second_number}, объект {pair.project}, "
                f"разница {pair.hours_apart} ч, совпали позиции: {', '.join(pair.materials)}"
            )

    if data.projects:
        lines += ["", "ОБЪЕКТЫ"]
        for project in data.projects:
            materials = f"; чаще всего: {', '.join(project.top_materials)}" if project.top_materials else ""
            lines.append(
                f"- {project.name}: в работе {project.active_count}, за месяц "
                f"{project.month_count} заявок на {money(project.month_amount)} сомони, "
                f"за нормативом {project.over_norm}{materials}"
            )

    if data.people:
        lines += ["", "У КОГО СЕЙЧАС ЗАЯВКИ"]
        for person in data.people:
            lines.append(
                f"- {person.name} ({person.role}): держит {person.holding}, "
                f"из них за нормативом {person.over_norm}; подал за месяц {person.created_month}"
            )

    lines += ["", "ИЗМЕНЕНИЯ К ПРОШЛОЙ НЕДЕЛЕ"]
    for trend in data.trends:
        change = "не с чем сравнить" if trend.change_pct is None else f"{trend.change_pct:+.1f}%".replace(".", ",")
        lines.append(
            f"- {trend.label}: сейчас {_num(trend.current, trend.unit)}, "
            f"неделей раньше {_num(trend.previous, trend.unit)} ({change})"
        )

    lines += ["", "ЧЕГО В ДАННЫХ НЕТ"]
    lines += [f"- {spot}" for spot in data.blind_spots]
    return "\n".join(lines)


def digest(session: Session, *, now: datetime | None = None) -> DigestOut:
    """Сводка для руководителя: цифры сервера плюс объяснение модели."""
    data = digest_facts(session, now=now)
    enabled = get_settings().assistant_enabled or assistant._transport is not None
    if not enabled:
        return data

    started = time.monotonic()
    try:
        text = assistant.ask(
            system=analytics_prompt(),
            prompt=(
                "Составь сводку для руководителя по данным ниже. Числа бери "
                "только отсюда.\n\nДАННЫЕ\n" + facts_block(data)
            ),
            schema=_Digest,
            effort="medium",
        )
    except assistant.AssistantError as exc:
        log.warning("Аналитик не ответил на сводку: %s", exc)
        ai_log.record(
            session,
            kind=AiKind.ANALYTICS,
            question="Сводка",
            ok=False,
            error=str(exc),
            duration_ms=_ms(started),
        )
        return data.model_copy(update={"ai": AiText(enabled=True, available=False)})

    # Сводка стоит денег на каждом заходе в раздел, поэтому она в журнале
    # наравне с вопросами: иначе счётчик обращений врёт о расходе.
    ai_log.record(
        session,
        kind=AiKind.ANALYTICS,
        question="Сводка",
        answer=text.headline,
        duration_ms=_ms(started),
    )

    return data.model_copy(
        update={
            "ai": AiText(
                enabled=True,
                available=True,
                headline=text.headline.strip() or None,
                summary=[s.strip() for s in text.summary if s.strip()][:5],
                recommendations=[r.strip() for r in text.recommendations if r.strip()][:3],
            )
        }
    )


def ask(
    session: Session,
    *,
    question: str,
    history: list[AnalyticsTurn] | None = None,
    now: datetime | None = None,
) -> AnalyticsReplyOut:
    """Вопрос руководителя обычными словами.

    Вопрос не превращается в SQL: модель видит те же факты, что и сводка,
    и отвечает по ним. Поэтому вопрос «покажи расходы директора» не может
    достать больше, чем система уже посчитала для этой роли.
    """
    enabled = get_settings().assistant_enabled or assistant._transport is not None
    if not enabled:
        return AnalyticsReplyOut(enabled=False, available=False)

    data = digest_facts(session, now=now)
    known = {brief.number: brief.id for brief in data.in_work}
    known.update({item.number: item.id for item in data.attention})
    known.update({p.first_number: p.first_id for p in data.duplicates})
    known.update({p.second_number: p.second_id for p in data.duplicates})

    turns = [(turn.role, turn.text) for turn in (history or [])][-MAX_HISTORY:]
    started = time.monotonic()
    try:
        reply = assistant.ask(
            system=analytics_prompt(),
            prompt=(
                f"Вопрос руководителя: {question.strip()}\n\n"
                "Отвечай только по данным ниже; чего в них нет — так и скажи.\n\n"
                "ДАННЫЕ\n" + facts_block(data)
            ),
            schema=_Answer,
            history=turns,
            effort="medium",
        )
    except assistant.AssistantError as exc:
        log.warning("Аналитик не ответил на вопрос: %s", exc)
        ai_log.record(
            session,
            kind=AiKind.ANALYTICS,
            question=question,
            ok=False,
            error=str(exc),
            duration_ms=_ms(started),
        )
        return AnalyticsReplyOut(enabled=True, available=False)

    ai_log.record(
        session,
        kind=AiKind.ANALYTICS,
        question=question,
        answer=reply.answer,
        duration_ms=_ms(started),
    )

    refs = [
        AnalyticsRequestRef(id=known[ref.number], number=ref.number, why=ref.why.strip())
        for ref in reply.requests
        # Номер, которого нет в фактах, модель придумала: ссылку не делаем.
        if ref.number in known
    ]
    return AnalyticsReplyOut(
        enabled=True,
        available=True,
        answer=reply.answer.strip(),
        bullets=[b.strip() for b in reply.bullets if b.strip()][:5],
        requests=refs[:10],
        recommendations=[r.strip() for r in reply.recommendations if r.strip()][:3],
    )


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
