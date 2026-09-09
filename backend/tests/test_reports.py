"""Сводки: доли, лимиты, бюджет, реестр выплат."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.models import Employee, PaymentMethod, Project
from app.schemas.request import (
    DecisionIn,
    ExpenseLineIn,
    PaymentIn,
    RequestCreate,
    SourcingIn,
    SourcingLineIn,
)
from app.services import reports as rep
from app.services import requests as svc


def add_request(session, employee, project, amount: str, *, approve=False, pay=False):
    """Заявка на заданную сумму, проведённая по пути закупки.

    Сумма появляется только после оценки закупа, поэтому «заявка на 1000»
    в отчётах — это всегда заявка, дошедшая как минимум до PRICED.
    """
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Расход", quantity=1)],
            submit=True,
        ),
    )
    svc.decide_request(session, request.id, DecisionIn(approve=True, actor="Руководитель"))
    svc.apply_sourcing(
        session,
        request.id,
        SourcingIn(lines=[SourcingLineIn(id=request.lines[0].id, price=amount)]),
        actor="Закуп",
    )
    if approve or pay:
        svc.decide_request(
            session, request.id, DecisionIn(approve=True, actor="Руководитель")
        )
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
    e = Employee(full_name="Мария Сидорова", position="Дизайнер")
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
    """Очередь считает оба шага руководителя по отдельности: сколько ждёт
    согласования покупки и сколько уже оценено закупом."""
    svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Расход", quantity=1)],
            submit=True,
        ),
    )
    add_request(session, employee, project, "2000.00")  # дошла до оценки
    session.flush()

    queue = rep.approval_queue(session)
    assert queue.count == 1
    assert queue.oldest_employee == "Иван Петров"
    assert queue.oldest_days == 0
    assert queue.priced_count == 1


def test_queue_empty(session) -> None:
    queue = rep.approval_queue(session)
    assert queue.count == 0
    assert queue.oldest_employee is None


def test_team_overview_counts_spent_per_employee(
    session, employee, project, second_employee
) -> None:
    add_request(session, employee, project, "3150.00", approve=True)

    year, month = rep.current_period()
    team = {m.full_name: m for m in rep.team_overview(session, year=year, month=month)}
    assert team["Иван Петров"].spent == Decimal("3150.00")
    assert team["Иван Петров"].requests_count == 1
    # Сотрудник без заявок попадает в таблицу с нулём, а не пропадает
    assert team["Мария Сидорова"].spent == Decimal("0.00")
    assert team["Мария Сидорова"].requests_count == 0


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


def test_overview_counts_stages_and_metrics(session, employee, project) -> None:
    """Дашборд: заявки раскладываются по этапам, выплаты месяца и
    отклонения считаются, очередь без права — пустая."""
    svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Черновик", quantity=1)],
            submit=False,
        ),
    )
    add_request(session, employee, project, "1000.00")  # PRICED
    add_request(session, employee, project, "2500.00", approve=True)  # APPROVED
    add_request(session, employee, project, "700.00", pay=True)  # PAID
    rejected = add_request(session, employee, project, "300.00")
    svc.decide_request(
        session,
        rejected.id,
        DecisionIn(approve=False, comment="Не нужно", actor="Руководитель"),
    )
    session.flush()

    year, month = rep.current_period()
    data = rep.overview(session, year=year, month=month)

    counts = {s.key: s.count for s in data.stages}
    assert counts == {"draft": 1, "pending": 0, "sourcing": 0, "priced": 1, "approved": 1}
    assert data.in_work == 3
    assert data.to_pay_amount == Decimal("2500.00")
    assert data.to_pay_count == 1
    assert data.paid_amount == Decimal("700.00")
    assert data.paid_count == 1
    assert data.avg_cycle_days == 0.0
    assert data.rejected_count == 1
    assert data.queue == [] and data.decisions == 0
    assert data.slowest_stage in {"Черновик", "Согласование суммы", "К оплате"}


def test_overview_scoped_to_employee(session, employee, second_employee, project) -> None:
    """Сотрудник видит на дашборде только свои заявки."""
    add_request(session, employee, project, "1000.00", approve=True)
    add_request(session, second_employee, project, "9000.00", approve=True)
    session.flush()

    year, month = rep.current_period()
    mine = rep.overview(session, year=year, month=month, employee_id=employee.id)
    everyone = rep.overview(session, year=year, month=month)
    assert mine.to_pay_amount == Decimal("1000.00")
    assert everyone.to_pay_amount == Decimal("10000.00")
    assert mine.in_work == 1 and everyone.in_work == 2


def test_decision_queue_skips_own_and_orders_by_wait(
    session, employee, second_employee, project
) -> None:
    """Очередь дашборда: чужие PENDING и PRICED, свои не считаются."""
    for who in (employee, second_employee):
        svc.create_request(
            session,
            RequestCreate(
                employee_id=who.id,
                project_id=project.id,
                lines=[ExpenseLineIn(title="Расход", quantity=1)],
                submit=True,
            ),
        )
    add_request(session, second_employee, project, "500.00")  # PRICED
    session.flush()

    rows, total, delayed = rep.decision_queue(session, decider_id=employee.id)
    assert total == 2
    assert delayed == 0
    assert {r.employee_id for r in rows} == {second_employee.id}
