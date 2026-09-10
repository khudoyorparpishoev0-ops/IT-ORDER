"""Аналитика по заявкам компании. Только чтение, только цифры.

Здесь считается всё, что руководитель спрашивает у системы: сколько
заявок открыто, где они стоят, что вышло за норматив, что похоже на
дубликат, как изменилась неделя. Модель ни одной цифры не считает —
`app/services/intelligence.py` отдаёт ей готовые факты и просит объяснить
словами. Иначе в сводке появлялись бы правдоподобные, но выдуманные
числа, а по ним принимают решения о деньгах.

Чего в ORDER нет и что поэтому здесь не считается: накладных и чеков
файлами (сравнивать сумму заявки не с чем — выплата проводится ровно на
сумму заявки), отделов (роль и этап заменяют их), приоритета заявки и
возврата на доработку (отклонение окончательно). Об этом честно
говорится в `blind_spots`, а не выдумывается.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.money import to_decimal
from app.core.permissions import Permission, has_permission
from app.core.time import (
    format_local_datetime,
    local_date,
    local_day_bounds,
    month_bounds,
    to_local,
    utcnow,
)
from app.db.models import (
    Employee,
    ExpenseLine,
    ExpenseRequest,
    Project,
    RequestStatus,
)
from app.schemas.analytics import (
    AttentionItem,
    DigestOut,
    DuplicatePair,
    PersonStat,
    ProjectStat,
    RequestBrief,
    StageStat,
    Totals,
    Trend,
)
from app.services.reports import get_budget
from app.services.requests import (
    IN_WORK_STATUSES,
    SPENT_STATUSES,
    awaiting_days,
    awaiting_label,
    awaiting_since,
    awaiting_stage,
    title_of,
)

#: Этапы пути в порядке движения заявки.
STAGES: tuple[tuple[RequestStatus, str, str], ...] = (
    (RequestStatus.DRAFT, "draft", "Черновик"),
    (RequestStatus.PENDING, "pending", "Согласование покупки"),
    (RequestStatus.SOURCING, "sourcing", "У закупа"),
    (RequestStatus.PRICED, "priced", "Согласование суммы"),
    (RequestStatus.APPROVED, "approved", "К оплате"),
)

#: Кто держит заявку на каждом этапе — словами, для сводки.
HOLDER = {
    "author": "Автор",
    "manager": "Руководитель",
    "procurement": "Отдел закупа",
    "finance": "Бухгалтерия",
    "closed": "Закрыта",
}

#: Право, без которого человек не может сдвинуть заявку с этапа.
STAGE_PERMISSION = {
    "manager": Permission.DECIDE_REQUEST,
    "procurement": Permission.SOURCE_REQUEST,
    "finance": Permission.PAY_REQUEST,
}

#: Во сколько раз превышение норматива считается критичным.
CRITICAL_FACTOR = 2

#: В каком окне ищем дубликаты, часов.
DUPLICATE_WINDOW_HOURS = 24 * 7

#: Во сколько раз сумма должна превышать обычную, чтобы её отметить.
UNUSUAL_AMOUNT_FACTOR = 3


def _norms() -> dict[RequestStatus, int | None]:
    """Нормативы времени на этапах, часов. Настраиваются в `.env`.

    У черновика норматива нет: он лежит у автора и компанию не задерживает.
    """
    settings = get_settings()
    return {
        RequestStatus.DRAFT: None,
        RequestStatus.PENDING: settings.sla_pending_hours,
        RequestStatus.SOURCING: settings.sla_sourcing_hours,
        RequestStatus.PRICED: settings.sla_priced_hours,
        RequestStatus.APPROVED: settings.sla_approved_hours,
    }


def _hours_on_stage(request: ExpenseRequest, now: datetime) -> int:
    """Сколько целых часов заявка стоит на текущем шаге."""
    since = awaiting_since(request)
    if since is None:
        return 0
    return max(0, int((now - since).total_seconds() // 3600))


def _normalize(title: str) -> str:
    """Название позиции для сравнения: без регистра, лишних знаков и цифр
    порядка. «Кабель UTP Cat6» и «кабель utp cat 6» — одно и то же."""
    text = re.sub(r"[^\w\s]", " ", title.lower())
    return " ".join(text.split())


def _keywords(title: str) -> set[str]:
    """Значимые слова названия. Короткие отбрасываем: по «на» и «для»
    совпадёт что угодно."""
    return {word for word in _normalize(title).split() if len(word) >= 4}


# --------------------------------------------------------------------------
# Сбор заявок
# --------------------------------------------------------------------------
def _in_work(session: Session) -> list[ExpenseRequest]:
    """Все незакрытые заявки со всем, что понадобится сводке."""
    return list(
        session.scalars(
            select(ExpenseRequest)
            .options(
                selectinload(ExpenseRequest.employee),
                selectinload(ExpenseRequest.project),
                selectinload(ExpenseRequest.lines),
            )
            .where(ExpenseRequest.status.in_(IN_WORK_STATUSES))
            .order_by(ExpenseRequest.created_at)
        )
    )


def _who_can_move(session: Session) -> dict[str, list[Employee]]:
    """Кто вообще способен сдвинуть заявку с каждого этапа.

    Пустой список — «некому решить»: роль есть в таблице прав, но живых
    сотрудников с ней в компании нет. Это худшая из задержек, потому что
    сама она не рассосётся.
    """
    people = list(session.scalars(select(Employee).where(Employee.active.is_(True))))
    return {
        stage: [p for p in people if has_permission(p.role, permission)]
        for stage, permission in STAGE_PERMISSION.items()
    }


# --------------------------------------------------------------------------
# Внимание руководителя
# --------------------------------------------------------------------------
def attention_list(
    session: Session,
    *,
    now: datetime | None = None,
    requests: list[ExpenseRequest] | None = None,
    limit: int = 20,
) -> list[AttentionItem]:
    """Заявки, на которые стоит посмотреть, с причинами.

    Причина всегда человеческая и проверяемая: «стоит 31 час при норме 8»,
    а не «выглядит подозрительно». Руководитель должен понимать, откуда
    взялась метка, иначе он перестанет ей верить.
    """
    now = now or utcnow()
    rows = _in_work(session) if requests is None else requests
    norms = _norms()
    movers = _who_can_move(session)
    unusual = _unusual_amount_threshold(rows)
    duplicate_numbers = {
        number
        for pair in find_duplicates(session, now=now, requests=rows)
        for number in (pair.first_number, pair.second_number)
    }

    items: list[AttentionItem] = []
    for request in rows:
        stage = awaiting_stage(request)
        norm = norms.get(request.status)
        hours = _hours_on_stage(request, now)
        reasons: list[str] = []
        level = "normal"

        if norm is not None and hours > norm:
            reasons.append(f"стоит {hours} ч при норме {norm} ч")
            level = "critical" if hours >= norm * CRITICAL_FACTOR else "attention"

        if stage in movers and not movers[stage]:
            reasons.append(f"некому решить: нет активных сотрудников роли «{HOLDER[stage]}»")
            level = "critical"

        if request.number in duplicate_numbers:
            reasons.append("похожа на другую заявку того же объекта")
            level = "critical" if level == "critical" else "attention"

        if unusual is not None and request.amount > unusual and request.status in SPENT_STATUSES:
            reasons.append("сумма заметно выше обычной по компании")
            level = "critical" if level == "critical" else "attention"

        missing_units = [line.title for line in request.lines if not (line.unit or "").strip()]
        if missing_units and request.status in (RequestStatus.PENDING, RequestStatus.SOURCING):
            reasons.append("в позициях не указана единица измерения")
            level = "critical" if level == "critical" else "attention"

        if not reasons:
            continue
        items.append(
            AttentionItem(
                id=request.id,
                number=request.number,
                title=title_of(request),
                project=request.project.name,
                employee=request.employee.full_name,
                holder=HOLDER.get(stage, stage),
                stage=stage,
                stage_label=awaiting_label(request),
                hours=hours,
                norm_hours=norm,
                level=level,  # type: ignore[arg-type]
                reasons=reasons,
                amount=request.amount,
                priced=request.amount > 0,
            )
        )

    order = {"critical": 0, "attention": 1, "normal": 2}
    items.sort(key=lambda i: (order[i.level], -i.hours))
    return items[:limit]


def _unusual_amount_threshold(rows: list[ExpenseRequest]) -> Decimal | None:
    """Порог «необычно высокой суммы» — по медиане оценённых заявок.

    Среднее для этого не годится: одна заявка на сто тысяч поднимет его
    так, что необычным не окажется уже ничто.
    """
    amounts = sorted(r.amount for r in rows if r.amount > 0)
    if len(amounts) < 4:
        return None
    median = amounts[len(amounts) // 2]
    return median * UNUSUAL_AMOUNT_FACTOR


# --------------------------------------------------------------------------
# Этапы
# --------------------------------------------------------------------------
def stage_stats(
    session: Session,
    *,
    now: datetime | None = None,
    requests: list[ExpenseRequest] | None = None,
) -> list[StageStat]:
    """Где стоят заявки и укладывается ли этап в норматив.

    Кроме того, что происходит сейчас, считается факт за 30 дней и за
    предыдущие 30: по одному срезу не видно, стало быстрее или медленнее.
    """
    now = now or utcnow()
    rows = _in_work(session) if requests is None else requests
    norms = _norms()
    done = _stage_durations(session, now=now)

    stats: list[StageStat] = []
    for status, key, label in STAGES:
        on_stage = [r for r in rows if r.status is status]
        hours = [_hours_on_stage(r, now) for r in on_stage]
        norm = norms.get(status)
        stats.append(
            StageStat(
                key=key,
                label=label,
                count=len(on_stage),
                avg_hours=round(sum(hours) / len(hours), 1) if hours else None,
                over_norm=sum(1 for h in hours if norm is not None and h > norm),
                norm_hours=norm,
                done_avg_hours=done["current"].get(key),
                done_prev_avg_hours=done["previous"].get(key),
            )
        )
    return stats


def _stage_durations(session: Session, *, now: datetime) -> dict[str, dict[str, float]]:
    """Сколько на деле занимал каждый этап у прошедших его заявок.

    Считается по отметкам времени самой заявки: подача → в закуп → оценка
    → решение → выплата. Событий журнала для этого не хватает: их пишет
    и человек, и система, а нужен факт перехода.
    """
    since = now - timedelta(days=60)
    rows = list(
        session.scalars(
            select(ExpenseRequest).where(ExpenseRequest.created_at >= since)
        )
    )
    edge = now - timedelta(days=30)
    buckets: dict[str, dict[str, list[float]]] = {
        "current": defaultdict(list),
        "previous": defaultdict(list),
    }
    pairs = (
        ("pending", "submitted_at", "sourcing_started_at"),
        ("sourcing", "sourcing_started_at", "sourced_at"),
        ("priced", "sourced_at", "decided_at"),
        ("approved", "decided_at", "paid_at"),
    )
    for request in rows:
        for key, start_field, end_field in pairs:
            start = getattr(request, start_field)
            end = getattr(request, end_field)
            if start is None or end is None or end < start:
                continue
            where = "current" if end >= edge else "previous"
            buckets[where][key].append((end - start).total_seconds() / 3600)

    return {
        window: {key: round(sum(v) / len(v), 1) for key, v in data.items() if v}
        for window, data in buckets.items()
    }


# --------------------------------------------------------------------------
# Объекты, люди, дубликаты, тренды
# --------------------------------------------------------------------------
def project_stats(
    session: Session,
    *,
    now: datetime | None = None,
    requests: list[ExpenseRequest] | None = None,
    limit: int = 8,
) -> list[ProjectStat]:
    """Объекты: сколько заявок в работе, сколько денег за месяц."""
    now = now or utcnow()
    rows = _in_work(session) if requests is None else requests
    norms = _norms()
    year, month = local_date(now).year, local_date(now).month
    start, end = month_bounds(year, month)

    month_rows = list(
        session.scalars(
            select(ExpenseRequest)
            .options(
                selectinload(ExpenseRequest.project),
                selectinload(ExpenseRequest.lines),
            )
            .where(ExpenseRequest.created_at >= start, ExpenseRequest.created_at < end)
        )
    )

    active: Counter[int] = Counter()
    over: Counter[int] = Counter()
    for request in rows:
        active[request.project_id] += 1
        norm = norms.get(request.status)
        if norm is not None and _hours_on_stage(request, now) > norm:
            over[request.project_id] += 1

    per_month: dict[int, list[ExpenseRequest]] = defaultdict(list)
    for request in month_rows:
        per_month[request.project_id].append(request)

    names = {
        pid: name
        for pid, name in session.execute(select(Project.id, Project.name)).all()
    }

    stats: list[ProjectStat] = []
    for pid in set(active) | set(per_month):
        month_list = per_month.get(pid, [])
        spent = sum(
            (r.amount for r in month_list if r.status in SPENT_STATUSES), Decimal("0")
        )
        materials = Counter(
            line.title.strip()
            for r in month_list
            for line in r.lines
            if line.title.strip()
        )
        stats.append(
            ProjectStat(
                id=pid,
                name=names.get(pid, "—"),
                active_count=active.get(pid, 0),
                month_count=len(month_list),
                month_amount=to_decimal(spent),
                over_norm=over.get(pid, 0),
                top_materials=[title for title, _ in materials.most_common(3)],
            )
        )
    stats.sort(key=lambda s: (-s.active_count, -s.month_count))
    return stats[:limit]


def people_stats(
    session: Session,
    *,
    now: datetime | None = None,
    requests: list[ExpenseRequest] | None = None,
    limit: int = 10,
) -> list[PersonStat]:
    """Сколько заявок ждёт каждого человека сейчас.

    Только факты: сколько держит и сколько из них вышло за норматив.
    Оценок работы здесь нет и быть не должно — выводы делает руководитель,
    который знает, кто был в отпуске, а кто на объекте без связи.
    """
    now = now or utcnow()
    rows = _in_work(session) if requests is None else requests
    norms = _norms()
    movers = _who_can_move(session)

    holding: Counter[int] = Counter()
    over: Counter[int] = Counter()
    for request in rows:
        stage = awaiting_stage(request)
        norm = norms.get(request.status)
        late = norm is not None and _hours_on_stage(request, now) > norm
        if stage == "author":
            holders = [request.employee] if request.employee.active else []
        else:
            # Заявка ждёт любого, кто вправе её сдвинуть; свою собственную
            # человек не решает, поэтому автор из списка выпадает.
            holders = [p for p in movers.get(stage, []) if p.id != request.employee_id]
        for person in holders:
            holding[person.id] += 1
            if late:
                over[person.id] += 1

    year, month = local_date(now).year, local_date(now).month
    start, end = month_bounds(year, month)
    created = dict(
        session.execute(
            select(ExpenseRequest.employee_id, func.count())
            .where(ExpenseRequest.created_at >= start, ExpenseRequest.created_at < end)
            .group_by(ExpenseRequest.employee_id)
        ).all()
    )

    people = {
        p.id: p for p in session.scalars(select(Employee).where(Employee.active.is_(True)))
    }
    stats = [
        PersonStat(
            id=pid,
            name=person.full_name,
            role=person.role.value,
            holding=holding.get(pid, 0),
            over_norm=over.get(pid, 0),
            created_month=int(created.get(pid, 0)),
        )
        for pid, person in people.items()
        if holding.get(pid) or created.get(pid)
    ]
    stats.sort(key=lambda s: (-s.over_norm, -s.holding))
    return stats[:limit]


def find_duplicates(
    session: Session,
    *,
    now: datetime | None = None,
    requests: list[ExpenseRequest] | None = None,
    limit: int = 10,
) -> list[DuplicatePair]:
    """Похожие заявки одного объекта, поданные близко по времени.

    Сравниваются значимые слова позиций: «UTP Cat6 305 м» и «кабель Cat6
    бухта» на одном объекте за неделю — повод проверить перед решением.
    Ничего не удаляется и не объединяется: заявка неизменяема, а решение
    принимает человек.
    """
    now = now or utcnow()
    rows = _in_work(session) if requests is None else requests
    window = timedelta(hours=DUPLICATE_WINDOW_HOURS)

    by_project: dict[int, list[ExpenseRequest]] = defaultdict(list)
    for request in rows:
        by_project[request.project_id].append(request)

    pairs: list[DuplicatePair] = []
    for group in by_project.values():
        group.sort(key=lambda r: r.created_at)
        for i, first in enumerate(group):
            for second in group[i + 1 :]:
                if second.created_at - first.created_at > window:
                    break
                shared = _shared_materials(first, second)
                if not shared:
                    continue
                pairs.append(
                    DuplicatePair(
                        first_id=first.id,
                        first_number=first.number,
                        second_id=second.id,
                        second_number=second.number,
                        project=first.project.name,
                        materials=shared,
                        hours_apart=int(
                            (second.created_at - first.created_at).total_seconds() // 3600
                        ),
                    )
                )
    pairs.sort(key=lambda p: p.hours_apart)
    return pairs[:limit]


def _shared_materials(first: ExpenseRequest, second: ExpenseRequest) -> list[str]:
    """Позиции, которые есть в обеих заявках."""
    shared: list[str] = []
    for line in first.lines:
        words = _keywords(line.title)
        if not words:
            continue
        for other in second.lines:
            if words & _keywords(other.title):
                shared.append(line.title.strip())
                break
    return shared[:3]


def trends(session: Session, *, now: datetime | None = None) -> list[Trend]:
    """Эта неделя против прошлой: заявки, расход, новые задержки.

    Рост сам по себе не нарушение, поэтому формулировка нейтральная:
    показатель отличается от обычного, стоит посмотреть почему.
    """
    now = now or utcnow()
    week = timedelta(days=7)
    this_start, prev_start = now - week, now - week * 2

    def count(start: datetime, end: datetime) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ExpenseRequest)
                .where(ExpenseRequest.created_at >= start, ExpenseRequest.created_at < end)
            )
            or 0
        )

    def spent(start: datetime, end: datetime) -> Decimal:
        return to_decimal(
            session.scalar(
                select(func.coalesce(func.sum(ExpenseRequest.amount), 0)).where(
                    ExpenseRequest.status.in_(SPENT_STATUSES),
                    ExpenseRequest.created_at >= start,
                    ExpenseRequest.created_at < end,
                )
            )
            or 0
        )

    def change(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    rows = [
        (
            "Подано заявок",
            float(count(this_start, now)),
            float(count(prev_start, this_start)),
            "заявок",
        ),
        (
            "Расход по заявкам",
            float(spent(this_start, now)),
            float(spent(prev_start, this_start)),
            "сомони",
        ),
    ]
    return [
        Trend(label=label, current=cur, previous=prev, change_pct=change(cur, prev), unit=unit)
        for label, cur, prev, unit in rows
    ]


# --------------------------------------------------------------------------
# Счётчики
# --------------------------------------------------------------------------
def totals(
    session: Session,
    *,
    now: datetime | None = None,
    requests: list[ExpenseRequest] | None = None,
    attention: list[AttentionItem] | None = None,
) -> Totals:
    now = now or utcnow()
    rows = _in_work(session) if requests is None else requests
    items = attention_list(session, now=now, requests=rows) if attention is None else attention
    norms = _norms()

    day_start, day_end = local_day_bounds(local_date(now))
    week_start = now - timedelta(days=7)
    year, month = local_date(now).year, local_date(now).month
    month_start, month_end = month_bounds(year, month)

    def count(*conditions) -> int:
        return int(
            session.scalar(
                select(func.count()).select_from(ExpenseRequest).where(*conditions)
            )
            or 0
        )

    closed = (RequestStatus.PAID, RequestStatus.FULFILLED)
    paid_month = list(
        session.scalars(
            select(ExpenseRequest).where(
                ExpenseRequest.status == RequestStatus.PAID,
                ExpenseRequest.paid_at >= month_start,
                ExpenseRequest.paid_at < month_end,
            )
        )
    )
    cycles = [
        (r.paid_at - r.submitted_at).total_seconds() / 86400
        for r in paid_month
        if r.paid_at is not None and r.submitted_at is not None
    ]

    to_pay = [r for r in rows if r.status is RequestStatus.APPROVED]
    budget = get_budget(session, year, month)
    spent_month = to_decimal(
        session.scalar(
            select(func.coalesce(func.sum(ExpenseRequest.amount), 0)).where(
                ExpenseRequest.status.in_(SPENT_STATUSES),
                ExpenseRequest.created_at >= month_start,
                ExpenseRequest.created_at < month_end,
            )
        )
        or 0
    )
    used_pct = None
    if budget is not None and budget.amount > 0:
        used_pct = int((spent_month / budget.amount * 100).to_integral_value())

    return Totals(
        active=sum(1 for r in rows if r.status is not RequestStatus.DRAFT),
        drafts=sum(1 for r in rows if r.status is RequestStatus.DRAFT),
        created_today=count(
            ExpenseRequest.created_at >= day_start, ExpenseRequest.created_at < day_end
        ),
        created_week=count(ExpenseRequest.created_at >= week_start),
        created_month=count(
            ExpenseRequest.created_at >= month_start, ExpenseRequest.created_at < month_end
        ),
        done_today=count(
            ExpenseRequest.status.in_(closed),
            ExpenseRequest.decided_at >= day_start,
            ExpenseRequest.decided_at < day_end,
        ),
        done_month=count(
            ExpenseRequest.status.in_(closed),
            ExpenseRequest.decided_at >= month_start,
            ExpenseRequest.decided_at < month_end,
        ),
        rejected_month=count(
            ExpenseRequest.status == RequestStatus.REJECTED,
            ExpenseRequest.decided_at >= month_start,
            ExpenseRequest.decided_at < month_end,
        ),
        critical=sum(1 for i in items if i.level == "critical"),
        attention=sum(1 for i in items if i.level == "attention"),
        over_norm=sum(
            1
            for r in rows
            if norms.get(r.status) is not None
            and _hours_on_stage(r, now) > (norms.get(r.status) or 0)
        ),
        to_pay_amount=to_decimal(sum((r.amount for r in to_pay), Decimal("0"))),
        to_pay_count=len(to_pay),
        paid_month_amount=to_decimal(sum((r.amount for r in paid_month), Decimal("0"))),
        paid_month_count=len(paid_month),
        budget_amount=budget.amount if budget else None,
        budget_used_pct=used_pct,
        avg_cycle_days=round(sum(cycles) / len(cycles), 1) if cycles else None,
    )


#: Чего ORDER не знает. Говорим прямо, чтобы руководитель не ждал от
#: сводки того, чего в данных нет.
BLIND_SPOTS = [
    "Накладных и чеков в ORDER нет: сверить сумму заявки не с чем — "
    "выплата всегда проводится ровно на сумму заявки.",
    "Отделов в системе нет. Вместо них — этапы: руководитель, отдел "
    "закупа, бухгалтерия.",
    "Приоритета у заявки нет, и возврата на доработку тоже: отклонение "
    "окончательно, исправление — это новая заявка.",
]


#: Сколько заявок отдаём модели списком. Больше — лишние деньги за
#: каждый вопрос, а частные вопросы обычно про свежие.
IN_WORK_LIMIT = 60


def in_work_briefs(
    session: Session,
    *,
    now: datetime | None = None,
    requests: list[ExpenseRequest] | None = None,
    limit: int = IN_WORK_LIMIT,
) -> list[RequestBrief]:
    """Короткие строки незакрытых заявок: свежие сверху."""
    now = now or utcnow()
    rows = _in_work(session) if requests is None else requests
    rows = sorted(rows, key=lambda r: r.created_at, reverse=True)[:limit]
    return [
        RequestBrief(
            id=r.id,
            number=r.number,
            title=title_of(r),
            project=r.project.name,
            employee=r.employee.full_name,
            holder=HOLDER.get(awaiting_stage(r), awaiting_stage(r)),
            hours=_hours_on_stage(r, now),
            amount=r.amount,
            priced=r.amount > 0,
        )
        for r in rows
    ]


def digest_facts(session: Session, *, now: datetime | None = None) -> DigestOut:
    """Полная картина без слов модели. Панель может показать её и без AI.

    Собирается один раз и переиспользуется: список незакрытых заявок
    читается из базы единожды, а не в каждой функции.
    """
    now = now or utcnow()
    rows = _in_work(session)
    items = attention_list(session, now=now, requests=rows)
    return DigestOut(
        generated_at=format_local_datetime(now),
        ai={"enabled": False, "available": False},
        totals=totals(session, now=now, requests=rows, attention=items),
        attention=items,
        in_work=in_work_briefs(session, now=now, requests=rows),
        stages=stage_stats(session, now=now, requests=rows),
        projects=project_stats(session, now=now, requests=rows),
        people=people_stats(session, now=now, requests=rows),
        duplicates=find_duplicates(session, now=now, requests=rows),
        trends=trends(session, now=now),
        blind_spots=BLIND_SPOTS,
    )
