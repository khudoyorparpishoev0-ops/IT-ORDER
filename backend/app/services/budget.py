"""Бюджет месяца: сколько компания готова потратить.

От него считаются проценты в «Финансах», доля в сводке на Обзоре и строка
в недельной рассылке. До сих пор он заводился только запросом к API —
то есть практически никем.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.money import money, to_decimal
from app.db.models import MonthlyBudget
from app.services.audit import write_audit

log = logging.getLogger(__name__)


def set_budget(
    session: Session, *, year: int, month: int, amount: Decimal
) -> MonthlyBudget:
    """Задаёт или меняет бюджет месяца.

    История правок остаётся в журнале действий: сумма месяца — решение, а
    не настройка, и потом важно, кто и когда её менял.
    """
    if not 1 <= month <= 12:
        raise ValidationError("Месяц вне диапазона 1–12")
    value = to_decimal(amount)
    if value < 0:
        raise ValidationError("Бюджет не может быть отрицательным")

    budget = session.scalar(
        select(MonthlyBudget).where(
            MonthlyBudget.year == year, MonthlyBudget.month == month
        )
    )
    period = f"{year}-{month:02d}"

    if budget is None:
        budget = MonthlyBudget(year=year, month=month, amount=value)
        session.add(budget)
        session.flush()
        write_audit(
            session,
            entity="budget",
            entity_id=period,
            action="create",
            details=f"{period}: {money(value)} сомони",
        )
        log.info("Бюджет %s задан: %s", period, value)
        return budget

    was = budget.amount
    budget.amount = value
    session.flush()
    write_audit(
        session,
        entity="budget",
        entity_id=period,
        action="update",
        # В журнале видно и старое значение: «стало 200 000» без «было»
        # не отвечает на вопрос, увеличили бюджет или урезали.
        details=f"{period}: было {money(was)} → стало {money(value)} сомони",
    )
    log.info("Бюджет %s изменён: %s → %s", period, was, value)
    return budget
