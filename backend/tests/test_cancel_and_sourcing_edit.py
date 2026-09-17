"""Отмена заявки и правка состава закупом.

Две вещи из служебной записки заказчика, которые до сих пор упирались в
одно и то же: заявка после подачи была неизменяема целиком. Если товар
не нашёлся, у закупа оставался единственный выход — вернуть заявку
руководителю с нулём или дождаться отказа. Теперь у «не нашли» есть свой
способ, и он не выглядит как решение руководителя.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import AuditLog, EventKind, ExpenseRequest, RequestStatus


def need(client, employee, project, lines=None) -> dict:
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": lines
            or [
                {"title": "Цемент М500", "quantity": 40, "unit": "мешок"},
                {"title": "Гофра 16 мм", "quantity": 100, "unit": "м"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, created: dict) -> dict:
    """Заявка из `need` уже подана: `submit` в теле по умолчанию true."""
    assert created["status"] == "pending", created["status"]
    return created


def approve(client, request_id: int) -> dict:
    response = client.post(
        f"/api/requests/{request_id}/decision", json={"approve": True}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# Отмена
# --------------------------------------------------------------------------
def test_author_cancels_own_request(client, login, employee, project) -> None:
    login(employee)
    created = submit(client, need(client, employee, project))
    response = client.post(
        f"/api/requests/{created['id']}/cancel", json={"reason": "Объект закрыли"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


def test_cancel_needs_a_reason(client, login, employee, project) -> None:
    """«Отменена» без объяснения через месяц не скажет ничего никому."""
    login(employee)
    created = submit(client, need(client, employee, project))
    response = client.post(f"/api/requests/{created['id']}/cancel", json={"reason": " "})
    assert response.status_code == 422


def test_procurement_cancels_what_lies_with_them(
    client, login, employee, manager, procurement, project
) -> None:
    """Закуп упирается в «этого нет в продаже» — и закрывает заявку сам."""
    login(employee)
    created = submit(client, need(client, employee, project))
    login(manager)
    approve(client, created["id"])

    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/cancel",
        json={"reason": "Снято с производства, замены нет"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


def test_procurement_cannot_cancel_what_is_not_theirs(
    client, login, employee, procurement, project
) -> None:
    """Пока заявка у руководителя, закуп в неё не вмешивается."""
    login(employee)
    created = submit(client, need(client, employee, project))
    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/cancel", json={"reason": "Не нашли"}
    )
    assert response.status_code == 403


def test_stranger_does_not_see_the_request_at_all(
    client, login, employee, session, project
) -> None:
    """Чужая заявка — 404, а не 403: иначе номера перебираются по коду."""
    from app.db.models import EmployeeRole
    from tests.conftest import make_employee

    login(employee)
    created = submit(client, need(client, employee, project))
    other = make_employee(
        session,
        full_name="Пётр Сидоров",
        email="p.sidorov@it-hona.tj",
        role=EmployeeRole.EMPLOYEE,
    )
    session.commit()
    login(other)
    response = client.post(
        f"/api/requests/{created['id']}/cancel", json={"reason": "Просто так"}
    )
    assert response.status_code == 404


def _service_request(session, employee, project):
    """Заявка через сервисный слой: тесты про запреты не про HTTP."""
    from app.schemas.request import ExpenseLineIn, RequestCreate
    from app.services import requests as svc

    return svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[
                ExpenseLineIn(title="Цемент М500", quantity=40, unit="мешок"),
                ExpenseLineIn(title="Гофра 16 мм", quantity=100, unit="м"),
            ],
            submit=True,
        ),
    )


def test_paid_request_cannot_be_cancelled(session, employee, project, advance) -> None:
    """Деньги ушли: «отменить» их задним числом нельзя — это уже возврат."""
    from app.core.errors import ConflictError
    from app.core.time import utcnow
    from app.db.models import PaymentMethod
    from app.schemas.request import CancelIn, PaymentIn
    from app.services import requests as svc

    request = _service_request(session, employee, project)
    advance(
        request,
        to="approved",
        prices={"Цемент М500": "85.00", "Гофра 16 мм": "3.50"},
    )
    svc.pay_request(
        session,
        request.id,
        PaymentIn(
            method=PaymentMethod.CARD,
            document="ПП-0001",
            paid_at=utcnow(),
            actor="ФИНАНСЫ",
        ),
    )
    assert request.status is RequestStatus.PAID
    with pytest.raises(ConflictError):
        svc.cancel_request(session, request.id, CancelIn(reason="Передумали"))


def test_cancellation_is_written_down(client, login, employee, project, session) -> None:
    """В истории — событие с причиной, в журнале — строка с именем."""
    login(employee)
    created = submit(client, need(client, employee, project))
    client.post(
        f"/api/requests/{created['id']}/cancel", json={"reason": "Нашли на складе"}
    )

    detail = client.get(f"/api/requests/{created['id']}").json()
    events = [event for event in detail["events"] if event["kind"] == "cancelled"]
    assert len(events) == 1
    assert "Нашли на складе" in events[0]["text"]
    assert events[0]["actor"] == employee.full_name

    actions = [
        row.action
        for row in session.scalars(
            select(AuditLog).where(AuditLog.entity == "request")
        )
    ]
    assert "cancel" in actions


def test_cancelled_request_is_not_an_expense(
    session, employee, project, advance
) -> None:
    """Отменённая заявка денег не стоила — как и отклонённая."""
    from app.schemas.request import CancelIn
    from app.services import requests as svc

    request = _service_request(session, employee, project)
    advance(request, to="priced", prices={"Цемент М500": "85.00", "Гофра 16 мм": "3.50"})
    svc.cancel_request(session, request.id, CancelIn(reason="Отпала необходимость"))
    assert request.status is RequestStatus.CANCELLED
    assert request.status not in svc.SPENT_STATUSES


# --------------------------------------------------------------------------
# Правка состава закупом
# --------------------------------------------------------------------------
def sourcing_body(request: dict, decisions: dict[str, dict]) -> dict:
    lines = []
    for line in request["lines"]:
        entry = {"id": line["id"], "from_stock": False, "price": "10.00"}
        entry.update(decisions.get(line["title"], {}))
        lines.append(entry)
    return {"lines": lines}


def in_sourcing(client, login, employee, manager, project) -> dict:
    login(employee)
    created = submit(client, need(client, employee, project))
    login(manager)
    approve(client, created["id"])
    return created


def test_procurement_drops_a_line_it_could_not_find(
    client, login, employee, manager, procurement, project
) -> None:
    created = in_sourcing(client, login, employee, manager, project)
    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/sourcing",
        json=sourcing_body(
            created,
            {"Гофра 16 мм": {"drop": True, "price": None}, "Цемент М500": {"price": "85.00"}},
        ),
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert [line["title"] for line in detail["lines"]] == ["Цемент М500"]
    assert Decimal(detail["amount"]) == Decimal("3400.00")


def test_dropping_everything_is_not_an_estimate(
    client, login, employee, manager, procurement, project
) -> None:
    """Снять всё — это «покупать нечего», а у такого исхода своя кнопка."""
    created = in_sourcing(client, login, employee, manager, project)
    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/sourcing",
        json=sourcing_body(
            created,
            {
                "Цемент М500": {"drop": True, "price": None},
                "Гофра 16 мм": {"drop": True, "price": None},
            },
        ),
    )
    assert response.status_code == 422
    assert "отмените заявку" in response.json()["detail"]


def test_procurement_corrects_wording_and_amount(
    client, login, employee, manager, procurement, project
) -> None:
    """Продаётся бухтой по 50 м — количество меняется, и это видно в истории."""
    created = in_sourcing(client, login, employee, manager, project)
    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/sourcing",
        json=sourcing_body(
            created,
            {
                "Гофра 16 мм": {
                    "title": "Гофра ПВХ 16 мм, бухта 50 м",
                    "quantity": 2,
                    "price": "175.00",
                },
                "Цемент М500": {"price": "85.00"},
            },
        ),
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    titles = sorted(line["title"] for line in detail["lines"])
    assert titles == ["Гофра ПВХ 16 мм, бухта 50 м", "Цемент М500"]
    assert Decimal(detail["amount"]) == Decimal("3750.00")

    edits = [e for e in detail["events"] if e["kind"] == "sourcing_edited"]
    assert len(edits) == 1
    rows = edits[0]["details"]["lines"]
    assert rows[0]["from"] == "Гофра 16 мм — 100 м"
    assert rows[0]["to"] == "Гофра ПВХ 16 мм, бухта 50 м — 2 м"


def test_untouched_composition_leaves_no_event(
    client, login, employee, manager, procurement, project
) -> None:
    """«Изменил» без изменений превращает ленту в шум и учит её не читать."""
    created = in_sourcing(client, login, employee, manager, project)
    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/sourcing",
        json=sourcing_body(created, {"Цемент М500": {"price": "85.00"}}),
    )
    assert response.status_code == 200, response.text
    assert not [e for e in response.json()["events"] if e["kind"] == "sourcing_edited"]


def test_dropped_line_is_gone_from_the_database(
    client, login, employee, manager, procurement, project, session
) -> None:
    created = in_sourcing(client, login, employee, manager, project)
    login(procurement)
    client.post(
        f"/api/requests/{created['id']}/sourcing",
        json=sourcing_body(
            created,
            {"Гофра 16 мм": {"drop": True, "price": None}, "Цемент М500": {"price": "85.00"}},
        ),
    )
    stored = session.scalar(
        select(ExpenseRequest).where(ExpenseRequest.id == created["id"])
    )
    session.refresh(stored)
    assert [line.title for line in stored.lines] == ["Цемент М500"]


def test_history_keeps_the_dropped_line(
    client, login, employee, manager, procurement, project
) -> None:
    """Строки в заявке больше нет, но в истории видно, что она была."""
    created = in_sourcing(client, login, employee, manager, project)
    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/sourcing",
        json=sourcing_body(
            created,
            {"Гофра 16 мм": {"drop": True, "price": None}, "Цемент М500": {"price": "85.00"}},
        ),
    )
    edits = [e for e in response.json()["events"] if e["kind"] == EventKind.SOURCING_EDITED.value]
    assert edits[0]["details"]["lines"][0]["to"] == "снята"
