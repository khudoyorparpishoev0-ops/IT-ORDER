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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit_context import current_actor
from app.core.time import utcnow
from app.db.models import AiInteraction, AiKind, AiSource

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
) -> int | None:
    """Пишет обращение и возвращает его id.

    Никогда не бросает: запись в журнал — не то, ради чего человек открыл
    форму, и её сбой не должен отнимать у него ответ помощника. Коммит
    здесь свой: эндпоинты помощника ничего не меняют и сами не коммитят,
    а без коммита запись пропала бы вместе с сессией.
    """
    actor = current_actor()
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
        ).where(AiInteraction.created_at >= since)
    ).one()
    total, failed, applied, avg_ms = row

    by_kind = session.execute(
        select(AiInteraction.kind, func.count())
        .where(AiInteraction.created_at >= since)
        .group_by(AiInteraction.kind)
    ).all()

    return {
        "days": days,
        "total": int(total or 0),
        "failed": int(failed or 0),
        "applied": int(applied or 0),
        "avg_seconds": round(float(avg_ms) / 1000, 1) if avg_ms else None,
        "by_kind": {kind.value: int(count) for kind, count in by_kind},
    }


def recent(session: Session, *, limit: int = 10) -> list[AiInteraction]:
    """Последние обращения — чтобы администратор видел, что помощник живой."""
    return list(
        session.scalars(
            select(AiInteraction).order_by(AiInteraction.created_at.desc()).limit(limit)
        )
    )
