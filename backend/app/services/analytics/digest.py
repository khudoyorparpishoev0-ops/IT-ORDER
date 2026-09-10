"""Утренняя и вечерняя сводки руководителю.

Утром — что есть сейчас и с чего начинать день. Вечером — что за день
сделали, что появилось нового и что остаётся на завтра.

Обе собираются из тех же функций, что и раздел в панели: второго набора
расчётов у сводок нет намеренно, иначе цифра в письме однажды разойдётся
с цифрой на экране, и никто не поймёт, какая настоящая.

Текст здесь фактический, без объяснений: словами его пересказывает
`services/intelligence.py`, если ключ модели задан. Без ключа сводка
уходит как есть — цифры полезны и без пересказа.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.text import plural
from app.core.time import to_local, utcnow
from app.db.models import ExpenseRequest, RequestStatus
from app.services.analytics import attention, executive
from app.services.analytics.executive import DONE_STATUSES

#: Сколько проблем перечисляем поимённо. Список из пятнадцати строк в
#: сообщении не читают — по нему пробегают глазами и закрывают.
TOP_PROBLEMS = 3


@dataclass(frozen=True)
class Digest:
    """Сводка за период: цифры и главные проблемы."""

    kind: str
    title: str
    lines: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    #: Числа для тех, кто собирает сообщение сам (бот, письмо, панель).
    overview: executive.Overview | None = None


def _top(session: Session, now: datetime) -> list[str]:
    items = attention.requires_attention(session, now=now, limit=TOP_PROBLEMS)
    return [
        f"{item.number} · {item.project} · {item.reasons[0]}"
        for item in items
        if item.reasons
    ]


def morning(session: Session, *, now: datetime | None = None) -> Digest:
    """Утренняя сводка: что есть сейчас и с чего начинать."""
    moment = now or utcnow()
    data = executive.overview(session, now=moment)
    local = to_local(moment)

    lines = [
        f"Активные: {data.active_requests}",
        f"Новые за вчера: {_created_yesterday(session, moment)}",
        f"Выполнено вчера: {_closed_yesterday(session, moment)}",
        f"Просрочено: {data.overdue}",
        f"Требуют внимания: {data.requires_attention}",
    ]
    return Digest(
        kind="morning",
        title=f"ORDER • {local.strftime('%H:%M')}",
        lines=lines,
        problems=_top(session, moment),
        overview=data,
    )


def evening(session: Session, *, now: datetime | None = None) -> Digest:
    """Вечерняя сводка: что сделали за день и что остаётся на завтра."""
    moment = now or utcnow()
    data = executive.overview(session, now=moment)

    left = data.requires_attention
    lines = [
        f"Создано за день: {data.created_today}",
        f"Выполнено: {data.completed_today}",
        f"Осталось активных: {data.active_requests}",
        f"Требуют внимания: {left}",
    ]
    if left:
        lines.append(
            f"На завтра: {left} {plural(left, 'заявка', 'заявки', 'заявок')}"
        )
    else:
        lines.append("На завтра ничего не висит.")

    return Digest(
        kind="evening",
        title="ORDER • итоги дня",
        lines=lines,
        problems=_top(session, moment),
        overview=data,
    )


def as_text(digest: Digest) -> str:
    """Сводка одним сообщением: для письма, Telegram и push."""
    parts = [digest.title, "", *digest.lines]
    if digest.problems:
        parts.append("")
        parts.append("Основные проблемы:")
        parts.extend(f"{i}. {text}" for i, text in enumerate(digest.problems, 1))
    return "\n".join(parts)


def _created_yesterday(session: Session, now: datetime) -> int:
    start, end = _yesterday(now)
    return int(
        session.scalar(
            select(func.count())
            .select_from(ExpenseRequest)
            .where(
                ExpenseRequest.submitted_at >= start,
                ExpenseRequest.submitted_at < end,
            )
        )
        or 0
    )


def _closed_yesterday(session: Session, now: datetime) -> int:
    start, end = _yesterday(now)
    return int(
        session.scalar(
            select(func.count())
            .select_from(ExpenseRequest)
            .where(
                ExpenseRequest.status.in_(DONE_STATUSES),
                ExpenseRequest.decided_at >= start,
                ExpenseRequest.decided_at < end,
            )
        )
        or 0
    )


def _yesterday(now: datetime) -> tuple[datetime, datetime]:
    """Вчерашние местные сутки границами в UTC."""
    local = to_local(now)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end_local = start_local + timedelta(days=1)
    return start_local, end_local


#: Статус, при котором заявка ещё в работе. Экспортируется для сводок.
ACTIVE = (
    RequestStatus.PENDING,
    RequestStatus.SOURCING,
    RequestStatus.PRICED,
    RequestStatus.APPROVED,
)
