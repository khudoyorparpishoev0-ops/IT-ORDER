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
from sqlalchemy.orm import Session, selectinload

from app.core.text import plural
from app.core.time import to_local, utcnow
from app.db.models import ExpenseRequest, RequestStatus
from app.config import get_settings
from app.services.analytics import attention, executive, sla, stale
from app.services.analytics.executive import DONE_STATUSES
from app.services.analytics.scope import Scope
from app.services.requests import awaiting_since

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


def _top(session: Session, now: datetime, scope: Scope | None = None) -> list[str]:
    items = attention.requires_attention(
        session, now=now, limit=TOP_PROBLEMS, scope=scope
    )
    return [
        f"{item.number} · {item.project} · {item.reasons[0]}"
        for item in items
        if item.reasons
    ]


def morning(
    session: Session, *, now: datetime | None = None, scope: Scope | None = None
) -> Digest:
    """Утренняя сводка: что есть сейчас и с чего начинать."""
    moment = now or utcnow()
    data = executive.overview(session, now=moment, scope=scope)
    local = to_local(moment)

    lines = [
        f"Активные: {data.active_requests}",
        f"Новые за вчера: {created_yesterday(session, moment)}",
        f"Выполнено вчера: {closed_yesterday(session, moment)}",
        f"Просрочено: {data.overdue}",
        f"Требуют внимания: {data.requires_attention}",
    ]
    return Digest(
        kind="morning",
        title=f"ORDER • {local.strftime('%H:%M')}",
        lines=lines,
        problems=_top(session, moment, scope),
        overview=data,
    )


def evening(
    session: Session, *, now: datetime | None = None, scope: Scope | None = None
) -> Digest:
    """Вечерняя сводка: что сделали за день и что остаётся на завтра."""
    moment = now or utcnow()
    data = executive.overview(session, now=moment, scope=scope)

    left = data.requires_attention
    delta = overdue_delta(session, now=moment)
    lines = [
        f"Создано за день: {data.created_today}",
        f"Выполнено: {data.completed_today}",
        f"Осталось активных: {data.active_requests}",
        f"Новых просрочек: {delta['new']}",
        f"Требуют внимания: {left}",
        "",
        "Из утренних просрочек:",
        f"• устранено: {delta['resolved']}",
        f"• осталось: {delta['left']}",
        f"• новых за день: {delta['new']}",
        "",
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
        problems=_top(session, moment, scope),
        overview=data,
    )


# --- Сравнение «утро → вечер» -----------------------------------------------
#
# Модель утреннюю сводку не помнит и помнить не должна: память модели —
# не источник истины. Базовую точку сервер пересчитывает по сохранённым
# отметкам времени, и результат не зависит от того, отправлялась ли
# утренняя сводка вообще.
#
# Сравниваем именно просрочки, а не всю очередь внимания: у дубля и
# нестыковки нет времени, и «устранить» их за день нельзя — они либо
# есть, либо нет.


def _morning_moment(now: datetime) -> datetime:
    """Момент утренней сводки в эти сутки."""
    hour = get_settings().reminder_hour
    return to_local(now).replace(hour=hour, minute=0, second=0, microsecond=0)


def _step_started(request: ExpenseRequest) -> tuple[RequestStatus, datetime] | None:
    """На каком шаге стояла заявка и с какого момента.

    Для закрытой берётся шаг, с которого её закрыли: оплаченная стояла в
    бухгалтерии с момента утверждения суммы, закрытая складом — у закупа,
    отклонённая — там, где её отклонили.
    """
    if request.status is RequestStatus.PAID:
        return RequestStatus.APPROVED, request.decided_at or request.created_at
    if request.status is RequestStatus.FULFILLED:
        return RequestStatus.SOURCING, request.sourcing_started_at or request.created_at
    if request.status is RequestStatus.REJECTED:
        # Отклонить могли и покупку, и сумму: различаем по тому, успел ли
        # закуп её оценить.
        if request.sourced_at is not None:
            return RequestStatus.PRICED, request.sourced_at
        return RequestStatus.PENDING, request.submitted_at or request.created_at
    started = awaiting_since(request)
    return (request.status, started) if started is not None else None


def _was_overdue_at(request: ExpenseRequest, moment: datetime) -> bool:
    """Была ли заявка просрочена в этот момент."""
    step = _step_started(request)
    if step is None:
        return False
    status, started = step
    norm = sla.norms().get(status)
    if norm is None or started > moment:
        return False
    return (moment - started).total_seconds() / 3600 >= norm


def overdue_delta(session: Session, *, now: datetime) -> dict[str, int]:
    """Что стало с утренними просрочками к вечеру.

    `resolved` — закрыты за день; `left` — всё ещё стоят; `new` —
    просрочились уже после утра.
    """
    morning_at = _morning_moment(now)
    day_start = morning_at.replace(hour=0, minute=0, second=0, microsecond=0)

    closed_today = list(
        session.scalars(
            select(ExpenseRequest)
            .options(selectinload(ExpenseRequest.lines))
            .where(
                ExpenseRequest.status.in_(DONE_STATUSES),
                ExpenseRequest.created_at >= day_start - timedelta(days=180),
            )
        )
    )
    resolved = sum(
        1
        for r in closed_today
        if _closed_at(r) is not None
        and _closed_at(r) >= day_start
        and _was_overdue_at(r, morning_at)
    )

    left = 0
    new = 0
    for request in stale.in_work(session):
        started = awaiting_since(request)
        norm = sla.norms().get(request.status)
        if norm is None or started is None:
            continue
        if (now - started).total_seconds() / 3600 < norm:
            continue
        if _was_overdue_at(request, morning_at):
            left += 1
        else:
            new += 1
    return {"resolved": resolved, "left": left, "new": new}


def _closed_at(request: ExpenseRequest) -> datetime | None:
    if request.status is RequestStatus.PAID:
        return request.paid_at or request.decided_at
    if request.status is RequestStatus.FULFILLED:
        return request.sourced_at
    return request.decided_at


def as_text(digest: Digest) -> str:
    """Сводка одним сообщением: для письма, Telegram и push."""
    parts = [digest.title, "", *digest.lines]
    if digest.problems:
        parts.append("")
        parts.append("Основные проблемы:")
        parts.extend(f"{i}. {text}" for i, text in enumerate(digest.problems, 1))
    return "\n".join(parts)


def created_yesterday(session: Session, now: datetime) -> int:
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


def closed_yesterday(session: Session, now: datetime) -> int:
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
