"""Сводка руководителя: одно число на показатель.

Отвечает на вопрос «всё ли нормально» за несколько секунд. Не витрина
графиков: у директора нет времени разглядывать двадцать диаграмм, ему
нужно понять, есть ли проблема, и куда нажать.

Каждое число здесь считает база. Модель эти цифры не пересчитывает и не
угадывает — она получает их готовыми и только объясняет словами.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.text import plural
from app.core.time import local_date, to_local, utcnow
from app.db.models import ExpenseRequest, RequestStatus
from app.services.analytics import inconsistencies as inc
from app.services.analytics import stale
from app.services.analytics.facts import find_duplicates
from app.services.analytics.scope import Scope
from app.services.requests import SPENT_STATUSES

#: Заявка закрыта: оплачена, закрыта складом или отклонена.
DONE_STATUSES = (RequestStatus.PAID, RequestStatus.FULFILLED, RequestStatus.REJECTED)


@dataclass(frozen=True)
class Problem:
    """Строка блока «требует внимания» на дашборде директора."""

    code: str
    label: str
    count: int
    severity: str


@dataclass(frozen=True)
class Overview:
    """Состояние компании одним экраном."""

    generated_at: str
    active_requests: int
    created_today: int
    completed_today: int
    #: Вышли за норматив своего этапа.
    overdue: int
    #: Стоят без движения дольше порога, но норматив ещё не нарушен.
    stuck: int
    #: Сколько заявок вообще требуют внимания — без двойного счёта.
    requires_attention: int
    #: Сумма незакрытых оценённых заявок.
    amount_active: Decimal
    problems: list[Problem] = field(default_factory=list)


def overview(
    session: Session, *, now: datetime | None = None, scope: Scope | None = None
) -> Overview:
    """Сводка руководителя. Все числа — из базы, ни одного от модели."""
    moment = now or utcnow()
    today = local_date(moment)
    rows = stale.in_work(session, scope=scope)

    stuck_rows = stale.stuck_requests(session, now=moment, rows=rows)
    overdue_ids = {s.request_id for s in stuck_rows if s.overdue}
    stuck_ids = {s.request_id for s in stuck_rows} - overdue_ids

    issues = inc.find_all(session, rows=rows)
    # Информационные замечания в счётчик внимания не идут: «не указана
    # единица» не то, ради чего директора отрывают от дел.
    issue_ids = {i.request_id for i in issues if i.severity in ("critical", "warning")}

    duplicates = find_duplicates(session, now=moment)
    duplicate_ids = {p.first_id for p in duplicates} | {p.second_id for p in duplicates}

    created_today = session.scalar(
        select(func.count())
        .select_from(ExpenseRequest)
        .where(
            ExpenseRequest.submitted_at.is_not(None),
            ExpenseRequest.submitted_at >= _day_start(moment),
        )
    )
    completed_today = sum(
        1
        for status_at in _closed_moments(session)
        if status_at is not None and to_local(status_at).date() == today
    )

    amount_active = sum(
        (r.amount for r in rows if r.status in SPENT_STATUSES), Decimal("0.00")
    )

    attention_ids = overdue_ids | stuck_ids | issue_ids | duplicate_ids
    # Подписи склоняются по числу: «1 просрочена», «2 просрочены»,
    # «5 просрочено». Несклонённое «2 возможные дубли» в отчёте
    # руководителю читается как небрежность — и справедливо.
    problems = [
        Problem(
            "overdue",
            plural(len(overdue_ids), "просрочена", "просрочены", "просрочено"),
            len(overdue_ids),
            "critical",
        ),
        Problem("stuck", "без движения", len(stuck_ids), "warning"),
        Problem(
            "inconsistencies",
            plural(len(issue_ids), "нестыковка", "нестыковки", "нестыковок"),
            len(issue_ids),
            "warning",
        ),
        Problem(
            "duplicates",
            plural(
                len(duplicate_ids),
                "возможный дубль",
                "возможных дубля",
                "возможных дублей",
            ),
            len(duplicate_ids),
            "info",
        ),
    ]

    return Overview(
        generated_at=to_local(moment).isoformat(),
        active_requests=len(rows),
        created_today=int(created_today or 0),
        completed_today=completed_today,
        overdue=len(overdue_ids),
        stuck=len(stuck_ids),
        requires_attention=len(attention_ids),
        amount_active=amount_active,
        problems=[p for p in problems if p.count > 0],
    )


def _day_start(moment: datetime) -> datetime:
    """Начало сегодняшних местных суток в UTC."""
    local = to_local(moment)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(moment.tzinfo) if moment.tzinfo else start


def _closed_moments(session: Session) -> list[datetime | None]:
    """Когда закрылись заявки: оплата, склад или отказ.

    Отдельным запросом, потому что момент закрытия у статусов разный:
    оплаченная закрылась выплатой, закрытая складом — решением закупа,
    отклонённая — решением руководителя.
    """
    rows = session.execute(
        select(
            ExpenseRequest.status,
            ExpenseRequest.paid_at,
            ExpenseRequest.sourced_at,
            ExpenseRequest.decided_at,
        ).where(
            ExpenseRequest.status.in_(DONE_STATUSES),
            ExpenseRequest.created_at >= utcnow() - timedelta(days=3),
        )
    ).all()

    moments: list[datetime | None] = []
    for status, paid_at, sourced_at, decided_at in rows:
        if status is RequestStatus.PAID:
            moments.append(paid_at or decided_at)
        elif status is RequestStatus.FULFILLED:
            moments.append(sourced_at)
        else:
            moments.append(decided_at)
    return moments
