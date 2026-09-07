"""Сводки: доли, лимиты, бюджет, реестр выплат."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.models import Employee, PaymentMethod, Project
from app.schemas.request import DecisionIn, ExpenseLineIn, PaymentIn, RequestCreate
from app.services import reports as rep
from app.services import requests as svc


def add_request(session, employee, project, amount: str, *, approve=False, pay=False):
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Расход", quantity=1, price=amount)],
            submit=True,
        ),
    )
    if approve and request.status.value == "pending":
        svc.decide_request(session, request.id, DecisionIn(approve=True))
    if pay:
        svc.pay_request(
            session, request.id, PaymentIn(method=PaymentMethod.CARD, document="ПП-0001")
        )
    session.flush()
    return request


@pytest.fixture
def second_project(session) -> Project:
    p = Project(name="Рекова 132")
    session.add(p)
    session.flush()
    return p


@pytest.fixture
def second_employee(session) -> Employee:
    e = Employee(
        full_name="Мария Сидорова", position="Дизайнер", monthly_limit=Decimal("4000.00")
    )
    session.add(e)
    session.flush()
    return e


def test_project_shares_sum_to_100(session, employee, project, second_project) -> None:
    """Округление вниз по каждой строке недобирает до 100 — разница уходит
    в наибольшую долю, иначе полосы на графике визуально не сходятся."""
    add_request(session, employee, project, "1000.00", approve=True)
    add_request(session, employee, second_project, "2000.00", approve=True)

    year, month = rep.current_period()
    shares = rep.shares_by_project(session, year=year, month=month)
    assert sum(s.pct for s in shares) == 100
    assert shares[0].name == "Рекова 132"
    assert shares[0].amount == Decimal("2000.00")


def test_project_shares_empty_without_data(session) -> None:
    year, month = rep.current_period()
    assert rep.shares_by_project(session, year=year, month=month) == []


def test_dashboard_counts_by_status(session, employee, project, budget) -> None:
    add_request(session, employee, project, "1000.00", approve=True)
    add_request(session, employee, project, "2000.00")  # ждёт решения

    year, month = rep.current_period()
    stats = rep.dashboard_stats(session, year=year, month=month)
    assert stats.total_requests == 2
    assert stats.approved_amount == Decimal("1000.00")
    assert stats.pending_amount == Decimal("2000.00")
    assert stats.budget_amount == Decimal("156000.00")
    # 3000 из 156000 — 2%
    assert stats.budget_used_pct == 2


def test_dashboard_without_budget(session, employee, project) -> None:
    add_request(session, employee, project, "1000.00", approve=True)
    year, month = rep.current_period()
    stats = rep.dashboard_stats(session, year=year, month=month)
    assert stats.budget_amount is None
    assert stats.budget_used_pct is None


def test_queue_reports_oldest(session, employee, project) -> None:
    add_request(session, employee, project, "2000.00")
    queue = rep.approval_queue(session)
    assert queue.count == 1
    assert queue.oldest_employee == "Иван Петров"
    assert queue.oldest_days == 0
    assert queue.auto_approve_threshold == Decimal("500.00")


def test_queue_empty(session) -> None:
    queue = rep.approval_queue(session)
    assert queue.count == 0
    assert queue.oldest_employee is None


def test_team_overview_computes_share_of_limit(
    session, employee, project, second_employee
) -> None:
    add_request(session, employee, project, "3150.00", approve=True)

    year, month = rep.current_period()
    team = {m.full_name: m for m in rep.team_overview(session, year=year, month=month)}
    # 3150 из 5000 — 63%
    assert team["Иван Петров"].pct == 63
    assert team["Иван Петров"].spent == Decimal("3150.00")
    assert team["Иван Петров"].requests_count == 1
    # Сотрудник без заявок попадает в таблицу с нулём, а не пропадает
    assert team["Мария Сидорова"].spent == Decimal("0.00")
    assert team["Мария Сидорова"].pct == 0


def test_team_member_without_limit_has_no_pct(session, project) -> None:
    person = Employee(full_name="Без лимита", position="Стажёр")
    session.add(person)
    session.flush()
    add_request(session, person, project, "700.00", approve=True)

    year, month = rep.current_period()
    row = next(
        m
        for m in rep.team_overview(session, year=year, month=month)
        if m.full_name == "Без лимита"
    )
    assert row.limit is None
    assert row.pct is None


def test_payments_register_totals(session, employee, project) -> None:
    add_request(session, employee, project, "3100.00", approve=True, pay=True)
    add_request(session, employee, project, "1480.00", approve=True, pay=True)

    year, month = rep.current_period()
    register = rep.payments_register(session, year=year, month=month)
    assert register.total == Decimal("4580.00")
    assert len(register.items) == 2
    assert "2 выплат" in register.summary


def test_payments_register_filters_by_project(
    session, employee, project, second_project
) -> None:
    add_request(session, employee, project, "3100.00", approve=True, pay=True)
    add_request(session, employee, second_project, "1480.00", approve=True, pay=True)

    year, month = rep.current_period()
    only = rep.payments_register(
        session, year=year, month=month, project_id=second_project.id
    )
    assert only.total == Decimal("1480.00")
    assert only.items[0].project_name == "Рекова 132"


def test_payments_register_empty(session) -> None:
    year, month = rep.current_period()
    register = rep.payments_register(session, year=year, month=month)
    assert register.total == Decimal("0.00")
    assert register.items == []
    assert "не было" in register.summary


def test_budget_info(session, employee, project, budget) -> None:
    add_request(session, employee, project, "6000.00", approve=True)
    year, month = rep.current_period()
    info = rep.budget_info(session, year=year, month=month)
    assert info.month_limit == Decimal("156000.00")
    assert info.used == Decimal("6000.00")
    assert info.remaining == Decimal("150000.00")
    assert info.week_payout == Decimal("6000.00")
    assert info.week_requests == 1


def test_monthly_facts_axis_starts_at_zero(session, employee, project) -> None:
    add_request(session, employee, project, "97000.00", approve=True)
    facts = rep.monthly_facts(session, months=6)
    assert len(facts) == 6
    # Последний месяц — текущий, значение в тысячах сомони
    assert facts[-1].value == 97
    # Месяцы без данных дают ноль, а не пропуск: ось идёт от нуля
    assert facts[0].value == 0
