"""Напоминания и недельная сводка.

Заявка не двигается сама: если она третий день лежит у одного человека,
об этом должен узнать он, а не автор, который уже всё сделал. Поэтому
напоминание уходит тому, у кого заявка стоит сейчас, и одним письмом на
человека — пять отдельных писем читают хуже, чем один список.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.mail import send_quietly as mail_quietly
from app.core.permissions import Permission, has_permission
from app.core.telegram import Message
from app.core.telegram import send_quietly as telegram_quietly
from app.core.time import local_day_bounds, to_local, utcnow
from app.db.models import Employee, ExpenseRequest, RequestStatus
from app.services import mail_templates as templates
from app.services.notifications import panel_url
from app.services.reports import budget_info, current_period
from app.services.requests import (
    SPENT_STATUSES,
    awaiting_days,
    awaiting_stage,
)

log = logging.getLogger(__name__)

#: Куда ведёт ссылка того, у кого заявка стоит.
STAGE_PATH: dict[str, str] = {
    "author": "/requests",
    "manager": "/approvals",
    "procurement": "/sourcing",
    "finance": "/requests?status=approved",
}

#: Что человеку предстоит сделать. Текст один и для письма, и для бота.
STAGE_ACTION: dict[str, str] = {
    "author": "ваш черновик так и не отправлен",
    "manager": "ждёт вашего решения",
    "procurement": "ждёт оценки закупа",
    "finance": "ждёт выплаты",
}

#: Право, которым определяется, кто может сдвинуть заявку с места.
STAGE_PERMISSION: dict[str, Permission] = {
    "manager": Permission.DECIDE_REQUEST,
    "procurement": Permission.SOURCE_REQUEST,
    "finance": Permission.PAY_REQUEST,
}

#: На каких шагах заявка вообще может залежаться. Оплаченные, закрытые
#: складом и отклонённые никого не ждут.
OPEN_STATUSES = (
    RequestStatus.DRAFT,
    RequestStatus.PENDING,
    RequestStatus.SOURCING,
    RequestStatus.PRICED,
    RequestStatus.APPROVED,
)


@dataclass
class StaleItem:
    """Одна залежавшаяся заявка в чьём-то списке."""

    request: ExpenseRequest
    days: int

    @property
    def line(self) -> str:
        from app.core.text import plural

        return (
            f"{self.request.number} · {self.request.project.name} · "
            f"{self.days} {plural(self.days, 'день', 'дня', 'дней')}"
        )


def stale_requests(session: Session, *, now: datetime | None = None) -> list[ExpenseRequest]:
    """Заявки, которые стоят на одном шаге дольше положенного."""
    moment = now or utcnow()
    limit = get_settings().stale_request_days

    open_requests = session.scalars(
        select(ExpenseRequest)
        .options(
            selectinload(ExpenseRequest.employee),
            selectinload(ExpenseRequest.project),
        )
        .where(ExpenseRequest.status.in_(OPEN_STATUSES))
        .order_by(ExpenseRequest.id)
    )
    return [
        request
        for request in open_requests
        if (awaiting_days(request, now=moment) or 0) >= limit
    ]


def _holders(session: Session, request: ExpenseRequest) -> list[Employee]:
    """Кому напоминать об этой заявке.

    Своя заявка не в счёт даже у руководителя: двигать её он всё равно не
    может, и напоминание было бы издевательством.
    """
    stage = awaiting_stage(request)
    if stage == "author":
        author = request.employee
        return [author] if author is not None and author.active else []

    permission = STAGE_PERMISSION.get(stage)
    if permission is None:
        return []

    candidates = session.scalars(
        select(Employee)
        .where(Employee.active.is_(True), Employee.notify_stale_requests.is_(True))
        .order_by(Employee.full_name)
    )
    return [
        person
        for person in candidates
        if has_permission(person.role, permission) and person.id != request.employee_id
    ]


def stale_digest(
    session: Session, *, now: datetime | None = None
) -> list[tuple[Employee, list[StaleItem]]]:
    """Список «человек → его залежавшиеся заявки», по одному письму на человека."""
    moment = now or utcnow()
    by_person: dict[int, tuple[Employee, list[StaleItem]]] = {}

    for request in stale_requests(session, now=moment):
        item = StaleItem(request=request, days=awaiting_days(request, now=moment) or 0)
        for person in _holders(session, request):
            if not person.notify_stale_requests:
                continue
            by_person.setdefault(person.id, (person, []))[1].append(item)

    return [
        (person, items)
        for person, items in by_person.values()
        # Порядок предсказуемый: одинаковый прогон — одинаковый результат.
        if items
    ]


def send_stale_reminders(session: Session, *, now: datetime | None = None) -> str:
    """Рассылает напоминания. Возвращает строку для журнала задач."""
    digest = stale_digest(session, now=now)
    sent = 0

    for person, items in digest:
        stage_path = STAGE_PATH.get(awaiting_stage(items[0].request), "/requests")
        url = panel_url(stage_path)
        lines = [item.line for item in items]

        if person.email:
            letter = templates.stale_requests(
                full_name=person.full_name,
                lines=lines,
                url=url,
            )
            letter.to = person.email
            mail_quietly(letter)
        if person.telegram_chat_id:
            from html import escape

            body = "\n".join(f"• {escape(line)}" for line in lines)
            telegram_quietly(
                Message(
                    chat_id=person.telegram_chat_id,
                    text=(
                        f"<b>Заявки ждут вас</b>\n{body}\n\n"
                        "Каждый день ожидания — это день, который человек "
                        "работает без нужного."
                    ),
                    button=("Открыть", url),
                )
            )
        if person.email or person.telegram_chat_id:
            sent += 1

    log.info("Напоминания о залежавшихся заявках: %s получателей", sent)
    return f"{sent} получателей, {len(digest)} списков"


@dataclass
class WeekSummary:
    """Что произошло за неделю — одинаково для письма и для бота."""

    start: date
    end: date
    submitted: int
    paid_count: int
    paid_amount: Decimal
    stale_count: int
    budget_limit: Decimal | None
    budget_used: Decimal
    budget_pct: int | None


def week_summary(session: Session, *, now: datetime | None = None) -> WeekSummary:
    """Сводка за прошедшую неделю (понедельник — воскресенье)."""
    moment = to_local(now or utcnow())
    # Понедельник прошлой недели: сводка приходит в понедельник и
    # рассказывает про уже закрытую неделю, а не про начавшуюся.
    last_monday = moment.date() - timedelta(days=moment.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    start, _ = local_day_bounds(last_monday)
    _, end = local_day_bounds(last_sunday)

    submitted = (
        session.scalar(
            select(func.count(ExpenseRequest.id)).where(
                ExpenseRequest.submitted_at >= start,
                ExpenseRequest.submitted_at < end,
            )
        )
        or 0
    )
    paid_count = (
        session.scalar(
            select(func.count(ExpenseRequest.id)).where(
                ExpenseRequest.paid_at >= start, ExpenseRequest.paid_at < end
            )
        )
        or 0
    )
    paid_amount = session.scalar(
        select(func.coalesce(func.sum(ExpenseRequest.amount), 0)).where(
            ExpenseRequest.paid_at >= start, ExpenseRequest.paid_at < end
        )
    ) or Decimal("0")

    year, month = current_period()
    budget = budget_info(session, year=year, month=month)

    return WeekSummary(
        start=last_monday,
        end=last_sunday,
        submitted=submitted,
        paid_count=paid_count,
        paid_amount=Decimal(paid_amount),
        stale_count=len(stale_requests(session, now=now)),
        budget_limit=budget.month_limit,
        budget_used=budget.used,
        budget_pct=budget.used_pct,
    )


def weekly_recipients(session: Session) -> list[Employee]:
    """Кому идёт сводка: те, кто видит отчёты и не отключил рассылку."""
    candidates = session.scalars(
        select(Employee)
        .where(Employee.active.is_(True), Employee.notify_weekly_budget.is_(True))
        .order_by(Employee.full_name)
    )
    return [p for p in candidates if has_permission(p.role, Permission.VIEW_REPORTS)]


def send_weekly_summary(session: Session, *, now: datetime | None = None) -> str:
    """Рассылает недельную сводку. Возвращает строку для журнала задач."""
    summary = week_summary(session, now=now)
    url = panel_url("/reports")
    sent = 0

    for person in weekly_recipients(session):
        if person.email:
            letter = templates.weekly_budget(full_name=person.full_name, summary=summary, url=url)
            letter.to = person.email
            mail_quietly(letter)
        if person.telegram_chat_id:
            telegram_quietly(
                Message(
                    chat_id=person.telegram_chat_id,
                    text=telegram_summary_text(summary),
                    button=("Открыть отчёты", url),
                )
            )
        if person.email or person.telegram_chat_id:
            sent += 1

    log.info("Недельная сводка отправлена %s получателям", sent)
    return f"{sent} получателей"


def telegram_summary_text(summary: WeekSummary) -> str:
    """Текст сводки для бота. В письме те же цифры, но с разметкой."""
    from app.core.money import money
    from app.core.text import plural

    period = f"{summary.start.strftime('%d.%m')}—{summary.end.strftime('%d.%m')}"
    lines = [
        f"<b>Неделя {period}</b>",
        f"Подано заявок: {summary.submitted}",
        f"Выплачено: {summary.paid_count} на {money(summary.paid_amount)} сомони",
    ]
    if summary.budget_limit is not None:
        used = f"{money(summary.budget_used)} из {money(summary.budget_limit)} сомони"
        if summary.budget_pct is not None:
            used += f" ({summary.budget_pct}%)"
        lines.append(f"Бюджет месяца: {used}")
    if summary.stale_count:
        lines.append(
            f"Стоит без движения: {summary.stale_count} "
            f"{plural(summary.stale_count, 'заявка', 'заявки', 'заявок')}"
        )
    return "\n".join(lines)
