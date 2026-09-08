"""Отдел закупа: кто оценивает заявки и что при этом происходит."""

from __future__ import annotations

import pytest


def need(client, employee, project, title="Материалы", quantity=2) -> dict:
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": title, "quantity": quantity, "unit": "мешок"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def answer(request: dict, price: str | None) -> dict:
    return {
        "lines": [
            {
                "id": line["id"],
                "from_stock": price is None,
                "price": price,
            }
            for line in request["lines"]
        ]
    }


@pytest.mark.parametrize("role_fixture", ["employee", "manager", "finance"])
def test_only_procurement_prices_requests(
    client, login, request, employee, manager, project, role_fixture
) -> None:
    login(employee)
    created = need(client, employee, project)
    login(manager)
    client.post(f"/api/requests/{created['id']}/decision", json={"approve": True})

    login(request.getfixturevalue(role_fixture))
    response = client.post(
        f"/api/requests/{created['id']}/sourcing", json=answer(created, "100.00")
    )
    assert response.status_code == 403


def test_procurement_cannot_decide_or_pay(
    client, login, employee, manager, procurement, project, pipeline
) -> None:
    """Закуп называет цену, но не решает и не платит."""
    login(employee)
    created = need(client, employee, project)
    pipeline(created["id"], manager=manager, buyer=procurement, to="priced")

    login(procurement)
    assert (
        client.post(
            f"/api/requests/{created['id']}/decision", json={"approve": True}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/requests/{created['id']}/payment",
            json={"method": "cash", "document": "РКО-9"},
        ).status_code
        == 403
    )


def test_procurement_sees_all_requests(
    client, login, employee, manager, procurement, project
) -> None:
    """Иначе закуп не найдёт заявку, которую ему передали."""
    login(employee)
    need(client, employee, project)

    login(procurement)
    listing = client.get("/api/requests", params={"all_periods": True}).json()
    assert listing["total"] == 1


def test_procurement_does_not_price_own_request(
    client, login, procurement, manager, project
) -> None:
    login(procurement)
    created = need(client, procurement, project)
    login(manager)
    client.post(f"/api/requests/{created['id']}/decision", json={"approve": True})

    login(procurement)
    response = client.post(
        f"/api/requests/{created['id']}/sourcing", json=answer(created, "100.00")
    )
    assert response.status_code == 403
    assert "собственную" in response.json()["detail"]


def test_admin_can_do_sourcing(
    client, login, employee, admin, project
) -> None:
    """У администратора есть все права — путь не должен вставать, если
    закупщик в отпуске."""
    login(employee)
    created = need(client, employee, project)
    login(admin)
    client.post(f"/api/requests/{created['id']}/decision", json={"approve": True})
    priced = client.post(
        f"/api/requests/{created['id']}/sourcing", json=answer(created, "100.00")
    )
    assert priced.status_code == 200, priced.text
    assert priced.json()["status"] == "priced"


def test_sourcing_result_is_visible_in_card(
    client, login, employee, manager, procurement, project, pipeline
) -> None:
    login(employee)
    created = need(client, employee, project)
    pipeline(
        created["id"],
        manager=manager,
        buyer=procurement,
        prices={"Материалы": "250.50"},
        to="priced",
    )

    login(employee)
    card = client.get(f"/api/requests/{created['id']}").json()
    assert card["status"] == "priced"
    assert card["priced"] is True
    assert card["amount"] == "501.00"
    assert card["sourced_by"] == procurement.full_name
    assert card["lines"][0]["price"] == "250.50"
    assert card["lines"][0]["from_stock"] is False


def test_stock_line_shows_no_price(
    client, login, employee, manager, procurement, project, pipeline
) -> None:
    login(employee)
    created = need(client, employee, project)
    pipeline(
        created["id"], manager=manager, buyer=procurement, prices={}, to="fulfilled"
    )

    login(employee)
    card = client.get(f"/api/requests/{created['id']}").json()
    assert card["status"] == "fulfilled"
    assert card["amount"] == "0.00"
    assert card["lines"][0]["from_stock"] is True
    assert card["lines"][0]["price"] is None


def test_sourcing_comment_reaches_the_card(
    client, login, employee, manager, procurement, project
) -> None:
    login(employee)
    created = need(client, employee, project)
    login(manager)
    client.post(f"/api/requests/{created['id']}/decision", json={"approve": True})

    login(procurement)
    body = answer(created, "120.00")
    body["comment"] = "Цена от поставщика на 08.09, действует три дня"
    response = client.post(f"/api/requests/{created['id']}/sourcing", json=body)
    assert response.status_code == 200, response.text
    assert "поставщика" in response.json()["sourcing_comment"]


# --------------------------------------------------------------------------
# У кого заявка сейчас
# --------------------------------------------------------------------------
def test_card_shows_who_holds_the_request(
    client, login, employee, manager, procurement, finance, project, pipeline
) -> None:
    """На каждом шаге видно, у кого заявка и кто может её двинуть."""
    login(employee)
    created = need(client, employee, project)

    card = client.get(f"/api/requests/{created['id']}").json()
    assert card["awaiting_stage"] == "manager"
    assert "руководителя" in card["awaiting_label"]
    assert manager.full_name in card["awaiting_people"]
    assert card["awaiting_days"] == 0

    pipeline(created["id"], manager=manager, buyer=procurement, to="sourcing")
    login(employee)
    card = client.get(f"/api/requests/{created['id']}").json()
    assert card["awaiting_stage"] == "procurement"
    assert card["awaiting_people"] == [procurement.full_name]


def test_awaiting_finance_after_approval(
    client, login, employee, manager, procurement, finance, project, pipeline
) -> None:
    login(employee)
    created = need(client, employee, project)
    pipeline(created["id"], manager=manager, buyer=procurement)

    login(employee)
    card = client.get(f"/api/requests/{created['id']}").json()
    assert card["awaiting_stage"] == "finance"
    assert card["awaiting_people"] == [finance.full_name]


def test_closed_request_waits_for_nobody(
    client, login, employee, manager, procurement, project, pipeline
) -> None:
    login(employee)
    created = need(client, employee, project)
    pipeline(
        created["id"], manager=manager, buyer=procurement, prices={}, to="fulfilled"
    )

    login(employee)
    card = client.get(f"/api/requests/{created['id']}").json()
    assert card["awaiting_stage"] == "closed"
    assert card["awaiting_people"] == []
    assert card["awaiting_days"] is None


def test_author_is_not_listed_as_approver(
    client, login, manager, procurement, admin, project, pipeline
) -> None:
    """Свою заявку руководитель не согласует — и в ожидающих не значится."""
    login(manager)
    created = need(client, manager, project)

    card = client.get(f"/api/requests/{created['id']}").json()
    assert manager.full_name not in card["awaiting_people"]
    assert admin.full_name in card["awaiting_people"]


def test_list_shows_holder_without_extra_queries(
    client, login, employee, manager, project
) -> None:
    """Строка списка тоже отвечает, у кого заявка: без открытия карточки."""
    login(employee)
    need(client, employee, project)
    listing = client.get("/api/requests", params={"all_periods": True}).json()
    row = listing["items"][0]
    assert row["awaiting_stage"] == "manager"
    assert "руководителя" in row["awaiting_label"]
