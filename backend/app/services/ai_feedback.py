"""Оценка ответа помощника человеком: подошло или нет и почему.

Зачем отдельно от журнала обращений. Там факт: спросили — ответили.
Здесь мнение: помогло или нет. Доля применённых ответов говорит, чем
пользуются; оценка говорит, что именно не так — не понял запрос, назвал
не тот материал, задал лишние вопросы. По первому видно, работает ли
помощник, по второму — что в нём чинить.

Оценивать можно только своё обращение: чужое не находится вовсе.
Передумал — оценка заменяется, а не копится второй строкой.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.models import AiFeedback, AiInteraction, Employee

#: Причины отказа. Список закрытый: свободный текст в статистике не
#: группируется, а «Другое» с комментарием закрывает остальные случаи.
REASONS: dict[str, str] = {
    "misunderstood": "Не понял запрос",
    "wrong_material": "Неправильный материал",
    "wrong_spec": "Неправильная характеристика",
    "bad_fix": "Неправильно исправил текст",
    "too_many_questions": "Лишние вопросы",
    "stale": "Неактуальная рекомендация",
    "other": "Другое",
}


def rate(
    session: Session,
    employee: Employee,
    *,
    interaction_id: int,
    useful: bool,
    reason: str | None = None,
    comment: str | None = None,
) -> AiFeedback:
    """Ставит оценку ответу. Повторная оценка заменяет прежнюю."""
    entry = session.get(AiInteraction, interaction_id)
    if entry is None or entry.employee_id != employee.id:
        # Как чужая заявка: по коду ответа нельзя выяснить, сколько раз
        # спрашивали коллеги.
        raise NotFoundError("Обращение не найдено")

    if reason is not None and reason not in REASONS:
        raise ValidationError("Неизвестная причина оценки")
    if useful:
        # У «полезно» причины нет: спрашивать, чем именно помогло, —
        # это лишний экран ради данных, которыми никто не пользуется.
        reason = None
        comment = None

    existing = session.scalar(
        select(AiFeedback).where(
            AiFeedback.interaction_id == interaction_id,
            AiFeedback.employee_id == employee.id,
        )
    )
    if existing is None:
        existing = AiFeedback(
            interaction_id=interaction_id,
            employee_id=employee.id,
            useful=useful,
            reason=reason,
            comment=(comment or "").strip()[:1000] or None,
        )
        session.add(existing)
    else:
        existing.useful = useful
        existing.reason = reason
        existing.comment = (comment or "").strip()[:1000] or None

    session.commit()
    return existing


def summary(session: Session, *, days: int = 30) -> dict[str, object]:
    """Сколько оценок и какие. Считает база, а не модель."""
    from datetime import timedelta

    from app.core.time import utcnow

    since = utcnow() - timedelta(days=days)
    useful, useless = session.execute(
        select(
            func.count().filter(AiFeedback.useful.is_(True)),
            func.count().filter(AiFeedback.useful.is_(False)),
        ).where(AiFeedback.created_at >= since)
    ).one()

    reasons = session.execute(
        select(AiFeedback.reason, func.count())
        .where(
            AiFeedback.created_at >= since,
            AiFeedback.useful.is_(False),
            AiFeedback.reason.is_not(None),
        )
        .group_by(AiFeedback.reason)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    total = int(useful or 0) + int(useless or 0)
    return {
        "useful": int(useful or 0),
        "useless": int(useless or 0),
        "useless_pct": round(int(useless or 0) * 100 / total) if total else None,
        "top_reasons": [
            {"reason": reason, "label": REASONS.get(reason, reason), "count": int(count)}
            for reason, count in reasons
        ],
    }
