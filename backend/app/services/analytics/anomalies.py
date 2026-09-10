"""Что отличается от обычного уровня.

Без машинного обучения и пока незачем: на объёмах ORDER обычная
статистика отвечает на те же вопросы и, в отличие от модели, объясняет
себя одной строкой — «на 60% больше, чем неделей раньше».

Формулировка важна не меньше расчёта. Отклонение — это не нарушение:
объект мог войти в активную фазу, а всплеск заявок означать, что стройка
пошла. Поэтому говорим «отличается от обычного уровня», а вывод делает
руководитель.

Сравниваем всегда с историей самой компании: текущие 7 дней против
предыдущих 7 и текущий месяц против предыдущего. Порогов «в абсолютных
сомони» здесь нет — у каждой компании свой масштаб.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import ExpenseLine, ExpenseRequest, Project, RequestStatus
from app.services.requests import SPENT_STATUSES

#: На сколько процентов показатель должен отклониться, чтобы это стоило
#: показывать. Ниже — обычные колебания, и шум из них делать незачем.
THRESHOLD_PCT = 40

#: Меньше этого числа сравнивать не с чем: рост с одной заявки до двух —
#: это «плюс 100%» и ничего не значит.
MIN_BASE = 3

#: Сколько отклонений показываем. Список из двадцати строк не читают.
LIMIT = 6


@dataclass(frozen=True)
class Anomaly:
    """Показатель, отличающийся от обычного уровня."""

    code: str
    #: Что именно отличается: «Заявки по объекту «Регар»».
    subject: str
    current: float
    previous: float
    change_pct: int
    unit: str
    #: Человеческая формулировка, уже без обвинений.
    detail: str
    #: warning | info
    severity: str


def _pct(current: float, previous: float) -> int | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100)


def _window(now: datetime, days: int, shift: int = 0) -> tuple[datetime, datetime]:
    end = now - timedelta(days=days * shift)
    return end - timedelta(days=days), end


def _counts(
    session: Session, start: datetime, end: datetime
) -> tuple[int, Decimal]:
    """Сколько заявок подано за окно и на какую сумму."""
    count = session.scalar(
        select(func.count())
        .select_from(ExpenseRequest)
        .where(
            ExpenseRequest.created_at >= start,
            ExpenseRequest.created_at < end,
            ExpenseRequest.status != RequestStatus.DRAFT,
        )
    )
    amount = session.scalar(
        select(func.coalesce(func.sum(ExpenseRequest.amount), 0)).where(
            ExpenseRequest.created_at >= start,
            ExpenseRequest.created_at < end,
            ExpenseRequest.status.in_(SPENT_STATUSES),
        )
    )
    return int(count or 0), Decimal(amount or 0)


def _by_project(
    session: Session, start: datetime, end: datetime
) -> dict[int, tuple[str, int, Decimal]]:
    rows = session.execute(
        select(
            ExpenseRequest.project_id,
            Project.name,
            func.count(),
            func.coalesce(
                func.sum(
                    case(
                        (ExpenseRequest.status.in_(SPENT_STATUSES), ExpenseRequest.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .join(Project, ExpenseRequest.project_id == Project.id)
        .where(
            ExpenseRequest.created_at >= start,
            ExpenseRequest.created_at < end,
            ExpenseRequest.status != RequestStatus.DRAFT,
        )
        .group_by(ExpenseRequest.project_id, Project.name)
    ).all()
    return {row[0]: (row[1], int(row[2]), Decimal(row[3] or 0)) for row in rows}


def _by_material(
    session: Session, start: datetime, end: datetime
) -> dict[str, tuple[str, int]]:
    rows = session.execute(
        select(ExpenseLine.normalized_text, func.max(ExpenseLine.title), func.count())
        .join(ExpenseRequest, ExpenseLine.request_id == ExpenseRequest.id)
        .where(
            ExpenseRequest.created_at >= start,
            ExpenseRequest.created_at < end,
            ExpenseRequest.status != RequestStatus.DRAFT,
            ExpenseLine.normalized_text != "",
        )
        .group_by(ExpenseLine.normalized_text)
    ).all()
    return {row[0]: (row[1], int(row[2])) for row in rows}


def find(session: Session, *, now: datetime | None = None) -> list[Anomaly]:
    """Всё, что отличается от обычного уровня. Пусто — всё как обычно."""
    moment = now or utcnow()
    found: list[Anomaly] = []

    def compare(
        code: str,
        subject: str,
        current: float,
        previous: float,
        unit: str,
        what: str,
    ) -> None:
        if previous < MIN_BASE and current < MIN_BASE:
            return
        change = _pct(current, previous)
        if change is None or abs(change) < THRESHOLD_PCT:
            return
        direction = "выше" if change > 0 else "ниже"
        found.append(
            Anomaly(
                code=code,
                subject=subject,
                current=current,
                previous=previous,
                change_pct=change,
                unit=unit,
                detail=(
                    f"{what} {direction} обычного уровня: {_fmt(current)} против "
                    f"{_fmt(previous)} за предыдущий такой же период "
                    f"({change:+d}%)"
                ),
                severity="warning" if abs(change) >= THRESHOLD_PCT * 2 else "info",
            )
        )

    # --- Компания целиком: неделя к неделе -------------------------------
    now_start, now_end = _window(moment, 7)
    prev_start, prev_end = _window(moment, 7, shift=1)
    count_now, amount_now = _counts(session, now_start, now_end)
    count_prev, amount_prev = _counts(session, prev_start, prev_end)
    compare("requests_week", "Заявки за неделю", count_now, count_prev, "заявок", "Число заявок")
    compare(
        "amount_week",
        "Расход за неделю",
        float(amount_now),
        float(amount_prev),
        "сомони",
        "Расход",
    )

    # --- Объекты ---------------------------------------------------------
    projects_now = _by_project(session, now_start, now_end)
    projects_prev = _by_project(session, prev_start, prev_end)
    for project_id, (name, count, amount) in projects_now.items():
        was_name, was_count, was_amount = projects_prev.get(project_id, (name, 0, Decimal(0)))
        del was_name
        compare(
            "project_amount",
            f"Объект «{name}»",
            float(amount),
            float(was_amount),
            "сомони",
            f"Расход по объекту «{name}»",
        )
        compare(
            "project_requests",
            f"Объект «{name}»",
            count,
            was_count,
            "заявок",
            f"Число заявок по объекту «{name}»",
        )

    # --- Материалы -------------------------------------------------------
    materials_now = _by_material(session, now_start, now_end)
    materials_prev = _by_material(session, prev_start, prev_end)
    for key, (title, count) in materials_now.items():
        _, was_count = materials_prev.get(key, (title, 0))
        compare(
            "material_frequency",
            title,
            count,
            was_count,
            "раз",
            f"«{title}» запрашивают",
        )

    found.sort(key=lambda a: (a.severity != "warning", -abs(a.change_pct)))
    return found[:LIMIT]


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}".replace(".", ",")
