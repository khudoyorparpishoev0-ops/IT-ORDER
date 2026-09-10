"""Журнал обращений к AI: кто спросил, что ответили, пригодилось ли.

Зачем он нужен. Помощник стоит денег и работает не всегда одинаково: то
модель отвечает за четыре секунды, то не отвечает вовсе. Без записи
вопрос «помогает он людям или мешает» решается на глаз, а по журналу
видно долю отказов, среднее время ответа и — главное — как часто человек
нажимает «Применить». Ответ, который никто не применяет, помощником не
является.

Чего здесь нет. Ключа Anthropic и любых секретов: в базу попадает только
то, что человек и так видел на экране, обрезанное по длине. Модели эта
таблица не показывается никогда — память помощника это сами заявки, а не
его прошлые ответы.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import assistant
from app.core.audit_context import current_actor
from app.config import get_settings
from app.core.text import plural
from app.core.time import utcnow
from app.db.models import AiInteraction, AiKind, AiResolvedBy, AiSource
from app.services import ai_pricing

log = logging.getLogger(__name__)

#: Сколько текста храним. Диалог целиком не нужен: журнал отвечает на
#: вопрос «о чём спрашивали», а не заменяет переписку.
TEXT_LIMIT = 2000


def _cut(text: str | None) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"


def record(
    session: Session,
    *,
    kind: AiKind,
    question: str | None,
    answer: str | None = None,
    ok: bool = True,
    error: str | None = None,
    duration_ms: int | None = None,
    source: AiSource = AiSource.WEB,
    usage: assistant.Usage | None = None,
    resolved_by: AiResolvedBy | None = None,
    offers_apply: bool = False,
) -> int | None:
    """Пишет обращение и возвращает его id.

    Никогда не бросает: запись в журнал — не то, ради чего человек открыл
    форму, и её сбой не должен отнимать у него ответ помощника. Коммит
    здесь свой: эндпоинты помощника ничего не меняют и сами не коммитят,
    а без коммита запись пропала бы вместе с сессией.
    """
    actor = current_actor()
    model = usage.model if usage else None
    tokens_in = usage.input_tokens if usage else None
    tokens_out = usage.output_tokens if usage else None
    if resolved_by is None and ok and usage is not None:
        resolved_by = AiResolvedBy.MODEL

    entry = AiInteraction(
        kind=kind,
        source=source,
        employee_id=actor.id if actor else None,
        username=actor.name if actor else None,
        question=_cut(question),
        answer=_cut(answer),
        ok=ok,
        error=_cut(error),
        duration_ms=duration_ms,
        model=model,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        # Цена берётся сейчас и больше не пересчитывается: прайс
        # Anthropic меняется, а расход за прошлый месяц должен остаться
        # тем, что мы за него заплатили.
        cost_usd=ai_pricing.cost(model, tokens_in, tokens_out),
        resolved_by=resolved_by,
        # False, а не NULL: кнопка «Применить» была и её пока не нажали.
        # Без этой разницы доля применённых делится и на те ответы, где
        # кнопки нет вовсе, и выходит заниженной.
        applied=False if offers_apply else None,
    )
    try:
        session.add(entry)
        session.commit()
        return entry.id
    except Exception:  # noqa: BLE001 — журнал не важнее ответа человеку
        log.warning("Не удалось записать обращение к AI", exc_info=True)
        session.rollback()
        return None


def mark_applied(
    session: Session, interaction_id: int, *, employee_id: int
) -> AiInteraction | None:
    """Отмечает, что человек воспользовался ответом, и отдаёт запись.

    Чужую запись не находим вовсе (как чужую заявку): иначе перебором
    номеров можно было бы узнать, сколько раз спрашивали коллеги.
    """
    entry = session.get(AiInteraction, interaction_id)
    if entry is None or entry.employee_id != employee_id:
        return None
    entry.applied = True
    session.commit()
    return entry


def stats(session: Session, *, days: int = 30) -> dict[str, object]:
    """Сводка по обращениям за период: сколько, сколько отказов, сколько
    пригодилось, как долго ждали."""
    since = utcnow() - timedelta(days=days)
    row = session.execute(
        select(
            func.count(),
            func.count().filter(AiInteraction.ok.is_(False)),
            func.count().filter(AiInteraction.applied.is_(True)),
            func.avg(AiInteraction.duration_ms).filter(AiInteraction.ok.is_(True)),
            # Знаменатель доли применённых — только те ответы, где кнопка
            # «Применить» была. У вопроса аналитику её нет, и делить на
            # него значит занижать долю у всех остальных.
            func.count().filter(AiInteraction.applied.is_not(None)),
        ).where(AiInteraction.created_at >= since)
    ).one()
    total, failed, applied, avg_ms, offered = row

    by_kind = session.execute(
        select(AiInteraction.kind, func.count())
        .where(AiInteraction.created_at >= since)
        .group_by(AiInteraction.kind)
    ).all()

    week = session.scalar(
        select(func.count())
        .select_from(AiInteraction)
        .where(AiInteraction.created_at >= utcnow() - timedelta(days=7))
    )
    tokens_in, tokens_out = session.execute(
        select(
            func.sum(AiInteraction.input_tokens), func.sum(AiInteraction.output_tokens)
        ).where(AiInteraction.created_at >= since)
    ).one()

    total = int(total or 0)
    failed = int(failed or 0)
    return {
        "days": days,
        "total": total,
        "failed": failed,
        "error_pct": round(failed * 100 / total) if total else None,
        "applied": int(applied or 0),
        "apply_rate_pct": (
            round(int(applied or 0) * 100 / int(offered)) if offered else None
        ),
        "avg_seconds": round(float(avg_ms) / 1000, 1) if avg_ms else None,
        "by_kind": {kind.value: int(count) for kind, count in by_kind},
        "total_week": int(week or 0),
        "input_tokens": int(tokens_in) if tokens_in else None,
        "output_tokens": int(tokens_out) if tokens_out else None,
    }


def recent(session: Session, *, limit: int = 10) -> list[AiInteraction]:
    """Последние обращения — чтобы администратор видел, что помощник живой."""
    return list(
        session.scalars(
            select(AiInteraction).order_by(AiInteraction.created_at.desc()).limit(limit)
        )
    )


def purge_old(session: Session, *, now=None) -> str:
    """Чистит журнал обращений по сроку хранения. Фоновая задача.

    Что при этом НЕ удаляется: заявки, их позиции и написания, журнал
    действий `audit_log`, история статусов. Они лежат в других таблицах и
    с этой не связаны ничем — ни ссылкой, ни каскадом. `ai_interactions`
    вспомогательный: по нему видно, помогает помощник или мешает, и
    больше ничего. Вместе с обращением уходит только оценка ответа
    (`ai_feedback`, каскадом): мнение о несуществующем ответе не значит
    ничего.

    Срок берётся из `AI_INTERACTIONS_RETENTION_DAYS`.
    """
    days = get_settings().ai_interactions_retention_days
    edge = (now or utcnow()) - timedelta(days=days)
    removed = session.execute(
        delete(AiInteraction).where(AiInteraction.created_at < edge)
    ).rowcount
    session.commit()
    log.info("Журнал AI: удалено записей старше %s дней: %s", days, removed)
    return (
        f"удалено {removed} {plural(removed, 'запись', 'записи', 'записей')} "
        f"старше {days} {plural(days, 'дня', 'дней', 'дней')}"
    )
