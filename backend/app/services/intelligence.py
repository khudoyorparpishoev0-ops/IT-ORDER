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
from app.core.time import utcnow as _utcnow
from app.schemas.analytics import (
    AnalyticsReplyOut,
    AnalyticsRequestRef,
    AnalyticsTurn,
    AiText,
    DigestOut,
)
from app.services import ai_log
from app.services.analytics import BLIND_SPOTS, digest_facts, intents
from app.services.analytics import scope as analytics_scope
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
        usage=assistant.last_usage(),
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
        usage=assistant.last_usage(),
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


# --------------------------------------------------------------------------
# ORDER Intelligence: объяснение готовой сводки руководителя
# --------------------------------------------------------------------------
def no_ai() -> AiText:
    """Модель выключена. Цифры от этого не портятся."""
    return AiText(enabled=False, available=False)


def overview_facts(data, queue, deviations) -> str:
    """Блок фактов для модели: только то, что уже посчитал сервер.

    Ни одной строки отсюда модель не додумывает: она получает готовые
    числа и пересказывает их словами. Список намеренно короткий — из
    тридцати заявок в объяснение попадут три, а платить пришлось бы за
    все тридцать.
    """
    lines = [
        "СОСТОЯНИЕ",
        f"Активных заявок: {data.active_requests}",
        f"Создано сегодня: {data.created_today}",
        f"Закрыто сегодня: {data.completed_today}",
        f"Просрочено по нормативу: {data.overdue}",
        f"Без движения: {data.stuck}",
        f"Требуют внимания: {data.requires_attention}",
        f"Сумма активных заявок: {data.amount_active} сомони",
    ]

    if queue:
        lines.append("")
        lines.append("ОЧЕРЕДЬ ВНИМАНИЯ (важное сверху)")
        for item in queue[:10]:
            lines.append(
                f"{item.number} · {item.project} · {item.employee} · "
                f"{item.stage_label} · {'; '.join(item.reasons[:2])}"
            )

    if deviations:
        lines.append("")
        lines.append("ОТЛИЧАЕТСЯ ОТ ОБЫЧНОГО УРОВНЯ")
        lines.extend(a.detail for a in deviations)

    lines.append("")
    lines.append("ЧЕГО В ДАННЫХ НЕТ")
    lines.extend(BLIND_SPOTS)
    return "\n".join(lines)


def explain_overview(session: Session, data, queue, deviations) -> AiText:
    """Слова поверх готовых чисел. Сбой модели цифры не отменяет.

    Обращение пишется в журнал наравне с остальными: сводка стоит денег
    на каждом заходе в раздел, и счётчик расхода не должен об этом
    умалчивать.
    """
    if not (get_settings().assistant_enabled or assistant._transport is not None):
        return no_ai()

    started = time.monotonic()
    try:
        text = assistant.ask(
            system=analytics_prompt(),
            prompt=(
                "Объясни руководителю состояние ORDER по данным ниже. Числа "
                "бери только отсюда; чего в данных нет — так и скажи. Если "
                "причина задержки неизвестна, пиши: «Причина задержки в "
                "системе не указана».\n\nДАННЫЕ\n"
                + overview_facts(data, queue, deviations)
            ),
            schema=_Digest,
            effort="medium",
        )
    except assistant.AssistantError as exc:
        log.warning("Аналитик не объяснил сводку: %s", exc)
        ai_log.record(
            session,
            kind=AiKind.ANALYTICS,
            question="Сводка руководителя",
            ok=False,
            error=str(exc),
            duration_ms=_ms(started),
        )
        return AiText(enabled=True, available=False)

    ai_log.record(
        session,
        kind=AiKind.ANALYTICS,
        question="Сводка руководителя",
        answer=text.headline,
        duration_ms=_ms(started),
        usage=assistant.last_usage(),
    )
    return AiText(
        enabled=True,
        available=True,
        headline=text.headline.strip() or None,
        summary=[s.strip() for s in text.summary if s.strip()][:5],
        recommendations=[r.strip() for r in text.recommendations if r.strip()][:3],
    )


# --------------------------------------------------------------------------
# «Спросить ORDER AI»: намерение выбирает модель, данные достаёт сервер
# --------------------------------------------------------------------------
class _Intent(BaseModel):
    """Какую из разрешённых возможностей аналитики спрашивают."""

    intent: str = Field(description="Одно имя из списка возможностей")


def _pick_intent(question: str) -> str:
    """Просит модель назвать намерение. Никаких данных ей при этом не даём.

    Отдельный запрос вместо «пусть сама сходит в базу»: SQL от модели —
    это произвольный запрос в боевую базу от имени приложения. Здесь она
    выбирает из списка, а исполняет выбранное сервер — тем же кодом, что
    уже проверен тестами и уже знает про права.

    Запрос дешёвый: вопрос и список имён, без единой цифры. Не ответила —
    берём общее состояние, а не отказываем человеку.
    """
    try:
        picked = assistant.ask(
            system=(
                "Ты определяешь, что именно спрашивают у аналитики ORDER. "
                "Ответь ровно одним именем возможности из списка. Ничего "
                "не добавляй и не объясняй."
            ),
            prompt=(
                f"Вопрос руководителя: {question.strip()}\n\n"
                f"Возможности:\n{intents.catalog()}"
            ),
            schema=_Intent,
            effort="low",
        )
    except Exception as exc:  # noqa: BLE001
        # Ловим шире, чем AssistantError: модель может вернуть ответ не по
        # схеме, и это не повод отказать человеку в ответе. Общее
        # состояние — разумное умолчание для любого вопроса.
        log.warning("Намерение не определено: %s", exc)
        return intents.DEFAULT
    name = (picked.intent or "").strip()
    return name if name in intents.REGISTRY else intents.DEFAULT


def _render(name: str, result) -> str:
    """Результат намерения — плоским текстом для модели.

    Никаких JSON-структур: модель пересказывает словами, а не разбирает
    схему, и лишние скобки — это только лишние токены.
    """
    if result is None:
        return "Данных нет."
    if isinstance(result, list):
        if not result:
            return "Ничего не найдено."
        return "\n".join(_line(item) for item in result[: intents.ROWS_LIMIT])
    if isinstance(result, dict):
        return "\n".join(f"{key}:\n{_render(key, value)}" for key, value in result.items())
    return _line(result)


def _line(item) -> str:
    """Одна строка результата. Поля берём те, что есть у объекта."""
    if isinstance(item, str):
        return item
    data = vars(item) if hasattr(item, "__dict__") else dict(item)
    if not data and hasattr(item, "model_dump"):
        data = item.model_dump()
    parts = []
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        if key.endswith("_id") or key in ("codes", "generated_at"):
            continue
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value[:3])
        parts.append(f"{key}={value}")
    return " · ".join(parts)


def ask_by_intent(
    session: Session,
    *,
    question: str,
    history: list[AnalyticsTurn] | None = None,
    now: datetime | None = None,
    scope=None,
) -> AnalyticsReplyOut:
    """Вопрос руководителя обычными словами через разрешённые намерения.

    Три шага, и ни на одном модель не касается базы: она называет
    намерение → сервер выполняет разрешённую функцию → она пересказывает
    полученное словами. Номер заявки становится ссылкой, только если он
    есть в фактах: выдуманный отбрасывается.
    """
    enabled = get_settings().assistant_enabled or assistant._transport is not None
    if not enabled:
        return AnalyticsReplyOut(enabled=False, available=False)

    moment = now or _utcnow()
    if scope is None:
        scope = analytics_scope.Scope(employee_id=0)

    name = _pick_intent(question)
    result = intents.run(session, name, scope=scope, now=moment)

    # Номера, которые сервер действительно отдал модели. Всё, чего здесь
    # нет, она придумала — ссылку на такое не делаем.
    known = _numbers(session, moment)

    turns = [(turn.role, turn.text) for turn in (history or [])][-MAX_HISTORY:]
    started = time.monotonic()
    try:
        reply = assistant.ask(
            system=analytics_prompt(),
            prompt=(
                f"Вопрос руководителя: {question.strip()}\n\n"
                f"Ниже — данные, которые сервер посчитал по запросу «{name}». "
                "Отвечай только по ним; чего в них нет — так и скажи. Если "
                "причина задержки неизвестна, пиши: «Причина задержки в "
                "системе не указана».\n\n"
                f"ДАННЫЕ ({name})\n{_render(name, result)}"
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
        question=f"[{name}] {question}",
        answer=reply.answer,
        duration_ms=_ms(started),
        usage=assistant.last_usage(),
    )

    refs = [
        AnalyticsRequestRef(id=known[ref.number], number=ref.number, why=ref.why.strip())
        for ref in reply.requests
        if ref.number in known
    ]
    return AnalyticsReplyOut(
        enabled=True,
        available=True,
        answer=reply.answer.strip(),
        bullets=[b.strip() for b in reply.bullets if b.strip()][:5],
        requests=refs[:5],
        recommendations=[r.strip() for r in reply.recommendations if r.strip()][:3],
    )


def _numbers(session: Session, now: datetime) -> dict[str, int]:
    """Номера заявок, которые сервер может подтвердить."""
    from app.services.analytics.stale import in_work

    return {r.number: r.id for r in in_work(session)}
