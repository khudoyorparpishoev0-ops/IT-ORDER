"""Аналитика для руководителя: цифры считает сервер, а не модель."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.db.models import Employee, EmployeeRole, RequestStatus
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import analytics
from app.services import requests as svc


def need(session, employee, project, titles, *, submit=True):
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[
                ExpenseLineIn(title=title, quantity=1, unit="шт.") for title in titles
            ],
            submit=submit,
        ),
    )
    session.flush()
    return request


def age(request, hours: int) -> None:
    """Отматывает время входа на текущий этап назад."""
    moment = utcnow() - timedelta(hours=hours)
    request.created_at = min(request.created_at, moment)
    if request.submitted_at is not None:
        request.submitted_at = moment


def test_request_within_norm_is_not_flagged(session, employee, project, manager) -> None:
    need(session, employee, project, ["Кабель UTP Cat6"])
    assert analytics.attention_list(session) == []


def test_over_norm_becomes_attention_then_critical(
    session, employee, project, manager
) -> None:
    """Превышение норматива — внимание, двойное превышение — критично."""
    slow = need(session, employee, project, ["Гофра 16 мм"])
    age(slow, 10)  # норматив согласования 8 часов
    session.flush()
    items = analytics.attention_list(session)
    assert [i.level for i in items] == ["attention"]
    assert "стоит 10 ч при норме 8 ч" in items[0].reasons[0]

    age(slow, 30)
    session.flush()
    assert analytics.attention_list(session)[0].level == "critical"


def test_nobody_can_move_is_critical(session, employee, project) -> None:
    """Заявка ждёт роль, которой в компании нет: сама она не сдвинется."""
    request = need(session, employee, project, ["Кабель"])
    session.flush()
    items = analytics.attention_list(session)
    assert items and items[0].level == "critical"
    assert any("некому решить" in reason for reason in items[0].reasons)
    assert items[0].holder == "Руководитель"


def test_own_request_does_not_count_as_holding(session, manager, project) -> None:
    """Свою заявку руководитель не согласует — она его и не ждёт."""
    need(session, manager, project, ["Кабель"])
    session.flush()
    holders = {p.name: p.holding for p in analytics.people_stats(session)}
    assert holders.get(manager.full_name, 0) == 0


def test_duplicates_found_by_shared_materials(session, employee, project, manager) -> None:
    first = need(session, employee, project, ["Кабель UTP Cat6 305 м"])
    second = need(session, employee, project, ["кабель utp cat6, бухта"])
    session.flush()

    pairs = analytics.find_duplicates(session)
    assert len(pairs) == 1
    assert {pairs[0].first_number, pairs[0].second_number} == {first.number, second.number}
    assert pairs[0].project == project.name


def test_different_materials_are_not_duplicates(session, employee, project, manager) -> None:
    need(session, employee, project, ["Кабель UTP Cat6"])
    need(session, employee, project, ["Перчатки рабочие"])
    session.flush()
    assert analytics.find_duplicates(session) == []


def test_stage_stats_count_and_norms(session, employee, project, manager) -> None:
    request = need(session, employee, project, ["Кабель"])
    age(request, 12)
    session.flush()

    stages = {s.key: s for s in analytics.stage_stats(session)}
    assert stages["pending"].count == 1
    assert stages["pending"].norm_hours == 8
    assert stages["pending"].over_norm == 1
    assert stages["pending"].avg_hours == 12.0
    assert stages["draft"].count == 0


def test_totals_count_work_and_drafts(session, employee, project, manager) -> None:
    need(session, employee, project, ["Кабель"])
    need(session, employee, project, ["Черновик"], submit=False)
    session.flush()

    totals = analytics.totals(session)
    assert totals.active == 1
    assert totals.drafts == 1
    assert totals.created_today == 2
    assert totals.done_today == 0


def test_trends_compare_two_weeks(session, employee, project, manager) -> None:
    old = need(session, employee, project, ["Кабель"])
    old.created_at = utcnow() - timedelta(days=10)
    need(session, employee, project, ["Гофра"])
    session.flush()

    by_label = {t.label: t for t in analytics.trends(session)}
    submitted = by_label["Подано заявок"]
    assert submitted.current == 1
    assert submitted.previous == 1
    assert submitted.change_pct == 0.0


def test_digest_facts_work_without_ai(session, employee, project, manager) -> None:
    """Без ключа модели сводка всё равно полная: цифры считает сервер."""
    request = need(session, employee, project, ["Кабель"])
    age(request, 20)
    session.flush()

    data = analytics.digest_facts(session)
    assert data.ai.enabled is False and data.ai.available is False
    assert data.totals.active == 1
    assert data.attention and data.attention[0].number == request.number
    assert data.blind_spots and "Накладных" in data.blind_spots[0]


def test_project_stats_show_month_and_materials(
    session, employee, project, manager, advance
) -> None:
    request = need(session, employee, project, ["Кабель UTP Cat6"])
    advance(request, to="priced", prices={"Кабель UTP Cat6": "1500.00"})
    session.flush()

    stats = {p.name: p for p in analytics.project_stats(session)}
    assert stats[project.name].month_count == 1
    assert stats[project.name].month_amount == request.amount
    assert stats[project.name].top_materials == ["Кабель UTP Cat6"]


@pytest.fixture
def second_manager(session) -> Employee:
    person = Employee(
        full_name="Сергей Иванов", position="Руководитель", role=EmployeeRole.MANAGER
    )
    session.add(person)
    session.flush()
    return person


def test_people_stats_show_who_holds_what(
    session, employee, project, manager, second_manager
) -> None:
    """Заявку ждёт каждый, кто вправе её сдвинуть."""
    request = need(session, employee, project, ["Кабель"])
    age(request, 20)
    session.flush()

    stats = {p.name: p for p in analytics.people_stats(session)}
    assert stats[manager.full_name].holding == 1
    assert stats[manager.full_name].over_norm == 1
    assert stats[second_manager.full_name].holding == 1
    assert stats[employee.full_name].created_month == 1


def test_paid_request_leaves_the_picture(
    session, employee, project, manager, finance, advance
) -> None:
    from app.db.models import PaymentMethod
    from app.schemas.request import PaymentIn

    request = need(session, employee, project, ["Кабель"])
    advance(request, to="approved", prices={"Кабель": "900.00"})
    svc.pay_request(
        session,
        request.id,
        PaymentIn(method=PaymentMethod.CARD, document="ПП-0001", actor="Финансы"),
    )
    session.flush()

    totals = analytics.totals(session)
    assert totals.active == 0
    assert totals.paid_month_count == 1
    assert analytics.attention_list(session) == []
    assert request.status is RequestStatus.PAID
