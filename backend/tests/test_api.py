"""API: коды ответов, фильтры, переводы ошибок домена в HTTP."""

from __future__ import annotations

from decimal import Decimal

BIG_LINES = [
    {"title": "Материалы", "quantity": 5, "price": "120.00"},
    {"title": "Такси", "quantity": 2, "price": "535.00"},
]


def create(client, employee, project, lines=None, submit=True):
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": lines or BIG_LINES,
            "submit": submit,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_reports_database(client) -> None:
    """База поднята. Схема в тестах создаётся напрямую, поэтому таблицы
    миграций нет — и это должно читаться как not_applied, а не как
    недоступная база."""
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["migrations"] == "not_applied"
    assert body["timezone"] == "Asia/Dushanbe"


def test_create_returns_detail(client, employee, project) -> None:
    body = create(client, employee, project)
    assert body["number"].startswith("РЗ-")
    assert body["status"] == "pending"
    assert Decimal(body["amount"]) == Decimal("1670.00")
    assert body["employee_name"] == "Иван Петров"
    assert body["project_name"] == "Вилла Колхозная"
    assert len(body["lines"]) == 2
    assert body["events"], "история должна содержать хотя бы создание"


def test_list_filters_by_status(client, employee, project) -> None:
    create(client, employee, project)
    create(client, employee, project, lines=[{"title": "Обед", "quantity": 1, "price": "30.00"}])

    pending = client.get("/api/requests", params={"status": "pending"}).json()
    approved = client.get("/api/requests", params={"status": "approved"}).json()
    assert pending["total"] == 1
    assert approved["total"] == 1
    assert pending["items"][0]["status"] == "pending"


def test_list_search_by_employee_name(client, employee, project) -> None:
    create(client, employee, project)
    found = client.get("/api/requests", params={"search": "петров"}).json()
    missing = client.get("/api/requests", params={"search": "сидорова"}).json()
    assert found["total"] == 1
    assert missing["total"] == 0


def test_list_pagination(client, employee, project) -> None:
    for _ in range(3):
        create(client, employee, project)
    page = client.get("/api/requests", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["limit"] == 2


def test_reject_without_comment_is_422(client, employee, project) -> None:
    request = create(client, employee, project)
    response = client.post(
        f"/api/requests/{request['id']}/decision", json={"approve": False}
    )
    assert response.status_code == 422


def test_reject_with_comment_succeeds(client, employee, project) -> None:
    request = create(client, employee, project)
    response = client.post(
        f"/api/requests/{request['id']}/decision",
        json={"approve": False, "comment": "Нет чеков", "actor": "Артём Ковалёв"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_double_decision_is_409(client, employee, project) -> None:
    request = create(client, employee, project)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})
    again = client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})
    assert again.status_code == 409


def test_unknown_request_is_404(client) -> None:
    assert client.get("/api/requests/99999").status_code == 404


def test_payment_flow(client, employee, project) -> None:
    request = create(client, employee, project)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})
    paid = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "card", "document": "ПП-0412"},
    )
    assert paid.status_code == 200
    body = paid.json()
    assert body["status"] == "paid"
    assert body["payment"]["document"] == "ПП-0412"


def test_employee_with_requests_cannot_be_deleted(client, employee, project) -> None:
    create(client, employee, project)
    response = client.delete(f"/api/employees/{employee.id}")
    assert response.status_code == 409


def test_duplicate_project_is_409(client, project) -> None:
    response = client.post("/api/projects", json={"name": project.name})
    assert response.status_code == 409


def test_request_without_lines_is_422(client, employee, project) -> None:
    response = client.post(
        "/api/requests",
        json={"employee_id": employee.id, "project_id": project.id, "lines": []},
    )
    assert response.status_code == 422
