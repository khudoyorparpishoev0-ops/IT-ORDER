"""Склад через API: кто что видит и чего не может даже запросом.

Отдельно от `test_stock.py`: там проверяется учёт, здесь — границы.
Панель прячет разделы по правам, но это удобство; отказывает сервер.
"""

from __future__ import annotations

from decimal import Decimal

from app.db.models import EmployeeRole
from tests.conftest import make_employee


def _receipt(client, warehouse_id: int, **kw) -> dict:
    payload = {
        "warehouse_id": warehouse_id,
        "lines": [{"title": "Цемент М500", "quantity": "40", "price": "85.00"}],
        **kw,
    }
    response = client.post("/api/stock/receipts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Границы прав
# --------------------------------------------------------------------------
def test_employee_does_not_see_stock(client, login, employee, warehouse) -> None:
    """Рядовой сотрудник склада не видит вовсе: его путь к складу — заявка."""
    login(employee)
    for path in ("/api/stock/overview", "/api/stock/items", "/api/stock/balances"):
        assert client.get(path).status_code == 403, path


def test_employee_cannot_post_documents(client, login, employee, warehouse) -> None:
    login(employee)
    response = client.post(
        "/api/stock/receipts",
        json={
            "warehouse_id": warehouse.id,
            "lines": [{"title": "Цемент", "quantity": "1"}],
        },
    )
    assert response.status_code == 403


def test_manager_sees_quantity_but_not_cost(
    client, login, keeper, manager, warehouse
) -> None:
    """Решение «купить или взять со склада» принимается по количеству.
    Закупочная цена — отдельное сведение и отдельное право."""
    login(keeper)
    document = _receipt(client, warehouse.id)
    assert document["total"] == "3400.00"
    assert document["lines"][0]["price"] == "85.00"

    login(manager)
    card = client.get(f"/api/stock/documents/{document['id']}")
    assert card.status_code == 200, card.text
    assert card.json()["total"] is None
    assert card.json()["lines"][0]["price"] is None

    overview = client.get("/api/stock/overview").json()
    assert overview["value"] is None

    balances = client.get("/api/stock/balances").json()
    assert balances[0]["quantity"] == "40.000"


def test_keeper_sees_cost(client, login, keeper, warehouse) -> None:
    login(keeper)
    _receipt(client, warehouse.id)
    assert client.get("/api/stock/overview").json()["value"] == "3400.00"


def test_manager_cannot_post_documents(client, login, manager, warehouse) -> None:
    login(manager)
    response = client.post(
        "/api/stock/receipts",
        json={
            "warehouse_id": warehouse.id,
            "lines": [{"title": "Цемент", "quantity": "1"}],
        },
    )
    assert response.status_code == 403


def test_keeper_does_not_create_warehouses(client, login, keeper) -> None:
    """Склад — структура компании, как объект: его заводит администратор."""
    login(keeper)
    response = client.post("/api/stock/warehouses", json={"name": "Склад на Рекова"})
    assert response.status_code == 403


def test_admin_creates_warehouse(client, login, admin, project) -> None:
    login(admin)
    response = client.post(
        "/api/stock/warehouses",
        json={"name": "Склад на Рекова", "project_id": project.id},
    )
    assert response.status_code == 201, response.text
    assert response.json()["project_name"] == project.name


def test_keeper_creates_nomenclature(client, login, keeper) -> None:
    """Позицию заводит кладовщик: ждать администратора в момент приёмки
    значит остановить приёмку."""
    login(keeper)
    response = client.post(
        "/api/stock/items", json={"name": "Профиль 60х27", "unit": "шт."}
    )
    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------
# Остаток не задаётся
# --------------------------------------------------------------------------
def test_no_endpoint_sets_a_balance(client, login, keeper, warehouse) -> None:
    """Цифру остатка нельзя ни записать, ни поправить — такого адреса нет.

    Это не право доступа, а устройство: остаток есть следствие движений.
    """
    login(keeper)
    assert client.post("/api/stock/balances", json={}).status_code == 405
    assert client.put("/api/stock/balances", json={}).status_code == 405
    assert client.patch("/api/stock/balances", json={}).status_code == 405


def test_quantity_in_item_patch_is_ignored(client, login, keeper, warehouse) -> None:
    """Подсунуть остаток в правку позиции тоже не выйдет: лишнее поле
    не имеет смысла, а количество берётся из движений."""
    login(keeper)
    _receipt(client, warehouse.id)
    item = client.get("/api/stock/items").json()[0]
    response = client.patch(
        f"/api/stock/items/{item['id']}", json={"quantity": "1000", "note": "проверка"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["quantity"] == "40.000"


# --------------------------------------------------------------------------
# Обычная работа
# --------------------------------------------------------------------------
def test_issue_over_balance_is_conflict(
    client, login, keeper, employee, warehouse
) -> None:
    login(keeper)
    _receipt(client, warehouse.id)
    item = client.get("/api/stock/items").json()[0]
    response = client.post(
        "/api/stock/issues",
        json={
            "warehouse_id": warehouse.id,
            "recipient_id": employee.id,
            "lines": [{"item_id": item["id"], "quantity": "41"}],
        },
    )
    assert response.status_code == 409, response.text
    assert "не хватает" in response.json()["detail"]

    # Остаток на месте: отказ ничего не сдвинул.
    assert client.get("/api/stock/balances").json()[0]["quantity"] == "40.000"


def test_issue_and_card(client, login, keeper, employee, project, warehouse) -> None:
    login(keeper)
    _receipt(client, warehouse.id)
    item = client.get("/api/stock/items").json()[0]
    issued = client.post(
        "/api/stock/issues",
        json={
            "warehouse_id": warehouse.id,
            "recipient_id": employee.id,
            "project_id": project.id,
            "lines": [{"item_id": item["id"], "quantity": "12"}],
        },
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["recipient_name"] == employee.full_name
    assert issued.json()["project_name"] == project.name

    card = client.get(f"/api/stock/items/{item['id']}").json()
    assert card["item"]["quantity"] == "28.000"
    assert [move["kind"] for move in card["moves"]] == ["ISSUE", "RECEIPT"]


def test_cancel_through_api(client, login, keeper, warehouse) -> None:
    login(keeper)
    document = _receipt(client, warehouse.id)
    response = client.post(
        f"/api/stock/documents/{document['id']}/cancel",
        json={"reason": "Привезли не то"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    assert client.get("/api/stock/balances").json() == []


def test_cancel_needs_a_reason(client, login, keeper, warehouse) -> None:
    login(keeper)
    document = _receipt(client, warehouse.id)
    response = client.post(
        f"/api/stock/documents/{document['id']}/cancel", json={"reason": ""}
    )
    assert response.status_code == 422


def test_unknown_document_is_not_found(client, login, keeper) -> None:
    login(keeper)
    assert client.get("/api/stock/documents/9999").status_code == 404


def test_documents_are_listed_newest_first(
    client, login, keeper, employee, warehouse
) -> None:
    login(keeper)
    _receipt(client, warehouse.id)
    item = client.get("/api/stock/items").json()[0]
    client.post(
        "/api/stock/issues",
        json={
            "warehouse_id": warehouse.id,
            "recipient_id": employee.id,
            "lines": [{"item_id": item["id"], "quantity": "1"}],
        },
    )
    numbers = [doc["number"] for doc in client.get("/api/stock/documents").json()]
    assert numbers[0].startswith("ВД-")
    assert numbers[1].startswith("ПР-")


def test_filter_by_kind(client, login, keeper, warehouse) -> None:
    login(keeper)
    _receipt(client, warehouse.id)
    assert client.get("/api/stock/documents?kind=ISSUE").json() == []
    assert len(client.get("/api/stock/documents?kind=RECEIPT").json()) == 1


def test_procurement_keeps_stock_rights(client, login, procurement, warehouse) -> None:
    """Сегодня именно закуп отвечает «нашлось на складе». Отнять у него
    склад значило бы сломать работающий путь заявки."""
    login(procurement)
    _receipt(client, warehouse.id)
    assert client.get("/api/stock/overview").json()["value"] is not None


def test_disabled_keeper_role_still_has_no_decisions(session) -> None:
    """Кладовщик ведёт склад и только его: ни решений, ни выплат."""
    from app.core.permissions import Permission, permissions_for

    rights = permissions_for(EmployeeRole.WAREHOUSE)
    assert Permission.MANAGE_STOCK in rights
    assert Permission.DECIDE_REQUEST not in rights
    assert Permission.PAY_REQUEST not in rights
    assert Permission.VIEW_ALL_REQUESTS not in rights


def test_stock_document_names_its_author(client, login, keeper, warehouse) -> None:
    """Имя берётся из сессии, а не из тела запроса."""
    login(keeper)
    document = _receipt(client, warehouse.id, comment="Поставка от 11.09")
    assert document["created_by"] == keeper.full_name


def test_receipt_needs_at_least_one_line(client, login, keeper, warehouse) -> None:
    login(keeper)
    response = client.post(
        "/api/stock/receipts", json={"warehouse_id": warehouse.id, "lines": []}
    )
    assert response.status_code == 422


def test_second_keeper_sees_the_same_stock(client, login, keeper, session, warehouse) -> None:
    """Склад общий: остаток не принадлежит тому, кто его оприходовал."""
    login(keeper)
    _receipt(client, warehouse.id)
    other = make_employee(
        session,
        full_name="Собир Назаров",
        position="Кладовщик",
        email="s.nazarov@it-hona.tj",
        role=EmployeeRole.WAREHOUSE,
    )
    session.commit()
    login(other)
    assert Decimal(client.get("/api/stock/balances").json()[0]["quantity"]) == Decimal(
        "40.000"
    )
