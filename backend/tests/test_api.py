"""API: коды ответов, фильтры, переводы ошибок домена в HTTP.

Все эндпоинты, кроме /health и входа, требуют сессии, поэтому тесты
работают через фикстуры ролей.
"""

from __future__ import annotations

from decimal import Decimal

#: Сотрудник описывает потребность: что нужно и сколько. Цен у него нет.
BIG_LINES = [
    {"title": "Материалы", "quantity": 5, "unit": "мешок"},
    {"title": "Скотч", "quantity": 2, "unit": "шт."},
]
PRICES = {"Материалы": "120.00", "Скотч": "535.00"}


def create(client, employee, project, lines=None, submit=True, expect=201):
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": lines or BIG_LINES,
            "submit": submit,
        },
    )
    assert response.status_code == expect, response.text
    return response.json() if expect == 201 else None


def test_health_is_open(client) -> None:
    """Проверка здоровья не требует входа: её опрашивает Docker."""
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["timezone"] == "Asia/Dushanbe"


def test_create_returns_detail(as_manager, manager, project) -> None:
    body = create(as_manager, manager, project)
    assert body["number"].startswith("РЗ-")
    assert body["status"] == "pending"
    # Суммы ещё нет: цены проставит закуп.
    assert Decimal(body["amount"]) == Decimal("0.00")
    assert body["priced"] is False
    assert body["lines"][0]["price"] is None
    assert body["project_name"] == "Вилла Колхозная"
    assert len(body["lines"]) == 2
    assert body["events"], "история должна содержать хотя бы создание"


def test_list_filters_by_status(
    client, login, employee, manager, procurement, project, pipeline
) -> None:
    login(employee)
    waiting = create(client, employee, project)
    priced = create(client, employee, project, lines=[{"title": "Обед", "quantity": 1}])
    pipeline(priced["id"], manager=manager, buyer=procurement, to="priced")

    login(manager)
    pending = client.get("/api/requests", params={"status": "pending"}).json()
    on_sourcing = client.get("/api/requests", params={"status": "priced"}).json()
    assert pending["total"] == 1
    assert pending["items"][0]["id"] == waiting["id"]
    assert on_sourcing["total"] == 1


def test_list_search_by_employee_name(as_manager, manager, project) -> None:
    create(as_manager, manager, project)
    found = as_manager.get("/api/requests", params={"search": "ковалёв"}).json()
    missing = as_manager.get("/api/requests", params={"search": "сидорова"}).json()
    assert found["total"] == 1
    assert missing["total"] == 0


def test_list_pagination(as_manager, manager, project) -> None:
    for _ in range(3):
        create(as_manager, manager, project)
    page = as_manager.get("/api/requests", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["limit"] == 2


def submit_as_employee(client, login, employee, manager, project) -> dict:
    """Сотрудник подаёт свою заявку, затем в клиенте снова руководитель.

    Подать заявку за другого не может даже руководитель — только админ,
    поэтому сценарий согласования всегда двухшаговый.
    """
    login(employee)
    request = create(client, employee, project)
    login(manager)
    return request


def test_reject_without_comment_is_422(client, login, employee, manager, project) -> None:
    request = submit_as_employee(client, login, employee, manager, project)
    response = client.post(
        f"/api/requests/{request['id']}/decision", json={"approve": False}
    )
    assert response.status_code == 422


def test_reject_with_comment_succeeds(client, login, employee, manager, project) -> None:
    request = submit_as_employee(client, login, employee, manager, project)
    response = client.post(
        f"/api/requests/{request['id']}/decision",
        json={"approve": False, "comment": "Нет чеков"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_decided_by_comes_from_session(
    client, login, employee, manager, procurement, project, pipeline
) -> None:
    """Имя согласующего берётся из сессии: клиент не может его подменить."""
    request = submit_as_employee(client, login, employee, manager, project)
    pipeline(request["id"], manager=manager, buyer=procurement, to="priced")

    login(manager)
    body = client.post(
        f"/api/requests/{request['id']}/decision",
        json={"approve": True, "actor": "Кто-то другой"},
    ).json()
    assert body["decided_by"] == manager.full_name


def test_second_decision_before_sourcing_is_409(
    client, login, employee, manager, project
) -> None:
    """Заявка ушла в закуп — второго решения на этом шаге быть не может."""
    request = submit_as_employee(client, login, employee, manager, project)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})
    again = client.post(
        f"/api/requests/{request['id']}/decision", json={"approve": True}
    )
    assert again.status_code == 409


def test_unknown_request_is_404(as_manager) -> None:
    assert as_manager.get("/api/requests/99999").status_code == 404


def test_payment_flow(
    client, login, manager, finance, procurement, employee, project, pipeline
) -> None:
    request = submit_as_employee(client, login, employee, manager, project)
    approved = pipeline(
        request["id"], manager=manager, buyer=procurement, prices=PRICES
    )
    assert approved["status"] == "approved"
    assert Decimal(approved["amount"]) == Decimal("1670.00")

    login(finance)
    paid = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "card", "document": "ПП-0412"},
    )
    assert paid.status_code == 200
    body = paid.json()
    assert body["status"] == "paid"
    assert body["payment"]["document"] == "ПП-0412"


def test_employee_with_requests_cannot_be_deleted(
    client, login, admin, employee, project
) -> None:
    login(employee)
    create(client, employee, project)
    login(admin)
    response = client.delete(f"/api/employees/{employee.id}")
    assert response.status_code == 409


def test_duplicate_project_is_409(client, login, admin, project) -> None:
    login(admin)
    response = client.post("/api/projects", json={"name": project.name})
    assert response.status_code == 409


def test_request_without_lines_is_422(as_manager, manager, project) -> None:
    response = as_manager.post(
        "/api/requests",
        json={"employee_id": manager.id, "project_id": project.id, "lines": []},
    )
    assert response.status_code == 422
