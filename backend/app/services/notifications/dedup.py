"""Защита от повторов и история доставок.

Автоматическая рассылка отличается от ручной одним: её никто не
остановит, если она пойдёт не туда. Одна и та же проблема, приходящая
каждые двадцать минут, за день приучает не открывать сообщения ORDER
вовсе — и тогда пропущено будет и важное.

Всё держится на уникальном `dedup_key`:

* сводка — `morning:<сотрудник>:<местная дата>`: в сутки одна, и два
  процесса не разошлют её дважды, потому что вставка либо проходит, либо
  нет;
* сигнал — `critical:<сотрудник>:<заявка>:<причина>`: пока проблема та
  же, сообщение то же.

Механизм тот же, что у фоновых задач (`services/jobs.py`): вставка с
`ON CONFLICT DO NOTHING`, гонку решает база. Своей системы блокировок в
проекте нет и заводить её не нужно — advisory lock живёт в сессии и при
падении воркера отпускается, а строка в таблице переживает и падение, и
перезапуск.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.time import utcnow
from app.db.models import Employee, IntelligenceDelivery, IntelligenceKind

log = logging.getLogger(__name__)


def digest_key(employee: Employee, kind: IntelligenceKind, day: date) -> str:
    return f"{kind.value.lower()}:{employee.id}:{day.isoformat()}"


def alert_key(employee: Employee, request_id: int, reason: str) -> str:
    return f"critical:{employee.id}:{request_id}:{reason}"


def claim(
    session: Session,
    *,
    employee: Employee,
    kind: IntelligenceKind,
    key: str,
    request_id: int | None = None,
    reason: str | None = None,
    channel: str = "telegram",
) -> IntelligenceDelivery | None:
    """Занимает отправку. None — её уже занял кто-то другой.

    Строка появляется ДО отправки, а не после: если процесс умрёт между
    вставкой и отправкой, повтора не будет. Пропущенная сводка — потеря
    на один день; тройная сводка — потеря доверия ко всей рассылке.
    """
    session.execute(
        insert(IntelligenceDelivery)
        .values(
            employee_id=employee.id,
            kind=kind,
            dedup_key=key,
            request_id=request_id,
            reason=reason,
            channel=channel,
            sent_count=0,
            result_count=0,
            ok=True,
            ai_used=False,
        )
        .on_conflict_do_nothing(index_elements=[IntelligenceDelivery.dedup_key])
    )
    session.commit()

    row = session.scalar(
        select(IntelligenceDelivery).where(IntelligenceDelivery.dedup_key == key)
    )
    if row is None or row.sent_count > 0 or row.delivered_at is not None:
        return None
    return row


def repeatable(session: Session, key: str, *, now: datetime | None = None) -> IntelligenceDelivery | None:
    """Сигнал, о котором пора напомнить. None — рано или уже устранено.

    Повтор разрешён только для важного и не чаще, чем раз в
    `CRITICAL_ALERT_REPEAT_HOURS`: напоминание, приходящее слишком часто,
    перестаёт быть напоминанием.
    """
    moment = now or utcnow()
    row = session.scalar(
        select(IntelligenceDelivery).where(IntelligenceDelivery.dedup_key == key)
    )
    if row is None or row.resolved_at is not None:
        return None
    if row.last_sent_at is None:
        return row
    hours = get_settings().critical_alert_repeat_hours
    if (moment - row.last_sent_at) < timedelta(hours=hours):
        return None
    return row


def mark_sent(
    session: Session,
    row: IntelligenceDelivery,
    *,
    result_count: int = 0,
    ai_used: bool = False,
    now: datetime | None = None,
) -> None:
    """Отмечает, что сообщение ушло."""
    moment = now or utcnow()
    row.delivered_at = moment
    row.last_sent_at = moment
    row.sent_count += 1
    row.result_count = result_count
    row.ai_used = ai_used
    row.ok = True
    row.error = None
    session.commit()


def mark_skipped(session: Session, row: IntelligenceDelivery, reason: str) -> None:
    """Отмечает, что отправлять было нечего.

    `delivered_at` остаётся пустым: сводку не отправляли, и метрики не
    должны утверждать обратное. Но ключ занят, и второй раз за этот день
    мы к человеку не придём.
    """
    row.delivered_at = None
    row.sent_count = 1
    row.result_count = 0
    row.ok = True
    row.error = reason[:1000]
    session.commit()


def mark_failed(session: Session, row: IntelligenceDelivery, error: str) -> None:
    """Отмечает неудачу. Строка остаётся: по ней видно, что мы пытались.

    Ключ занят, поэтому повторных попыток в этот день не будет. Это
    осознанно: бесконечная переотправка при недоступном Telegram
    превращает рассылку в цикл, а недоставленная сводка видна в метриках
    и разбирается человеком.
    """
    row.ok = False
    row.error = error[:1000]
    session.commit()


def resolve_gone(
    session: Session, employee: Employee, still_open: set[str], *, now: datetime | None = None
) -> int:
    """Закрывает сигналы, проблем по которым больше нет.

    Отдельного сообщения об этом не шлём: «всё починилось» — не новость,
    ради которой стоит отвлекать. Число уходит в вечернюю сводку строкой
    «из отмеченных проблем устранено N».
    """
    moment = now or utcnow()
    rows = session.scalars(
        select(IntelligenceDelivery).where(
            IntelligenceDelivery.employee_id == employee.id,
            IntelligenceDelivery.kind == IntelligenceKind.CRITICAL,
            IntelligenceDelivery.resolved_at.is_(None),
        )
    ).all()
    closed = 0
    for row in rows:
        if row.dedup_key not in still_open:
            row.resolved_at = moment
            closed += 1
    if closed:
        session.commit()
    return closed


def resolved_today(
    session: Session, employee: Employee, *, now: datetime | None = None
) -> int:
    """Сколько отмеченных проблем закрылось за сегодня."""
    from app.core.time import to_local

    moment = now or utcnow()
    day_start = to_local(moment).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = session.scalars(
        select(IntelligenceDelivery).where(
            IntelligenceDelivery.employee_id == employee.id,
            IntelligenceDelivery.kind == IntelligenceKind.CRITICAL,
            IntelligenceDelivery.resolved_at.is_not(None),
            IntelligenceDelivery.resolved_at >= day_start,
        )
    ).all()
    return len(rows)
