"""Бюджет месяца задаётся из панели, а не только запросом к API."""

from __future__ import annotations

from decimal import Decimal

from app.db.models import AuditLog, MonthlyBudget
from app.services import budget as svc


def test_finance_sets_the_budget(client, login, finance, session):
    login(finance)
    response = client.put(
        "/api/reports/budget?year=2026&month=9", json={"amount": "150000.00"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["month_limit"] == "150000.00"

    saved = session.query(MonthlyBudget).filter_by(year=2026, month=9).one()
    assert saved.amount == Decimal("150000.00")


def test_manager_only_looks_at_the_budget(client, login, manager):
    """Руководитель бюджет видит, но не назначает: это деньги, не отчёт."""
    login(manager)
    assert client.get("/api/reports/budget").status_code == 200
    assert (
        client.put("/api/reports/budget?year=2026&month=9", json={"amount": "1000"}).status_code
        == 403
    )


def test_employee_sees_nothing(client, login, employee):
    login(employee)
    assert client.get("/api/reports/budget").status_code == 403


def test_change_is_recorded_with_the_old_value(client, login, finance, session):
    login(finance)
    client.put("/api/reports/budget?year=2026&month=9", json={"amount": "100000"})
    client.put("/api/reports/budget?year=2026&month=9", json={"amount": "80000"})

    entries = (
        session.query(AuditLog)
        .filter_by(entity="budget")
        .order_by(AuditLog.id)
        .all()
    )
    assert [e.action for e in entries] == ["create", "update"]
    # По журналу должно быть видно, урезали бюджет или подняли.
    # Разряды разделяются неразрывным пробелом — так их не разорвёт перенос.
    assert "было 100\u00a0000,00" in entries[1].details
    assert "стало 80\u00a0000,00" in entries[1].details
    assert entries[1].username == finance.full_name


def test_months_are_independent(client, login, finance, session):
    login(finance)
    client.put("/api/reports/budget?year=2026&month=9", json={"amount": "100000"})
    client.put("/api/reports/budget?year=2026&month=10", json={"amount": "120000"})

    september = client.get("/api/reports/budget?year=2026&month=9").json()
    october = client.get("/api/reports/budget?year=2026&month=10").json()
    assert september["month_limit"] == "100000.00"
    assert october["month_limit"] == "120000.00"


def test_negative_budget_is_rejected(client, login, finance):
    login(finance)
    response = client.put(
        "/api/reports/budget?year=2026&month=9", json={"amount": "-1"}
    )
    assert response.status_code == 422


def test_month_out_of_range_is_rejected(session):
    """Проверка на уровне сервиса: до API такой месяц не доходит."""
    import pytest

    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        svc.set_budget(session, year=2026, month=13, amount=Decimal("1"))
