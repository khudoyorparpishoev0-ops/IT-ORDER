"""Проверки по итогам аудита: заведение с паролем, даты выплат, разделение
обязанностей и отказ вместо 500 на пустых полях."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.time import utcnow
from tests.conftest import TEST_PASSWORD, make_employee


@pytest.fixture
def as_admin(client, admin, login):
    login(admin)
    return client


def create_request(client, employee, project, price="1500.00") -> dict:
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Материалы", "quantity": 1, "price": price}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Заведение сотрудника одним запросом
# --------------------------------------------------------------------------
def test_employee_and_password_in_one_request(as_admin, client) -> None:
    created = as_admin.post(
        "/api/employees",
        json={
            "full_name": "Далер Сафаров",
            "email": "d.safarov@it-hona.tj",
            "password": "первый-длинный-пароль",
        },
    )
    assert created.status_code == 201, created.text

    client.post("/api/auth/logout")
    entered = client.post(
        "/api/auth/login",
        json={"email": "d.safarov@it-hona.tj", "password": "первый-длинный-пароль"},
    )
    assert entered.status_code == 200, entered.text
    assert entered.json()["status"] == "ok"


def test_weak_password_creates_nobody(as_admin) -> None:
    """Слабый пароль отклоняется ДО создания: половинчатых карточек нет."""
    response = as_admin.post(
        "/api/employees",
        json={"full_name": "Слабый Пароль", "email": "weak@it-hona.tj", "password": "123"},
    )
    assert response.status_code == 422
    assert "короче" in response.json()["detail"]

    names = [e["full_name"] for e in as_admin.get("/api/employees").json()]
    assert "Слабый Пароль" not in names


def test_password_without_email_is_rejected(as_admin) -> None:
    response = as_admin.post(
        "/api/employees", json={"full_name": "Без Почты", "password": "длинный-пароль-тут"}
    )
    assert response.status_code == 422
    assert "почт" in response.json()["detail"].lower()

    names = [e["full_name"] for e in as_admin.get("/api/employees").json()]
    assert "Без Почты" not in names


def test_employee_without_password_still_works(as_admin) -> None:
    """Пароль необязателен: карточку можно завести и выдать доступ позже."""
    created = as_admin.post(
        "/api/employees", json={"full_name": "Позже Доступ", "email": "later@it-hona.tj"}
    )
    assert created.status_code == 201
    access = {row["id"]: row for row in as_admin.get("/api/employees/access").json()}
    assert access[created.json()["id"]]["has_password"] is False


# --------------------------------------------------------------------------
# Пустые значения вместо 500
# --------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["full_name", "position", "role", "active"])
def test_required_employee_fields_cannot_be_nulled(as_admin, employee, field) -> None:
    response = as_admin.patch(f"/api/employees/{employee.id}", json={field: None})
    assert response.status_code == 422, response.text
    assert "нельзя очистить" in response.json()["detail"]


@pytest.mark.parametrize("field", ["name", "active"])
def test_required_project_fields_cannot_be_nulled(as_admin, project, field) -> None:
    response = as_admin.patch(f"/api/projects/{project.id}", json={field: None})
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# Даты выплат
# --------------------------------------------------------------------------
def test_payment_in_the_future_is_rejected(client, login, employee, manager, finance, project) -> None:
    login(employee)
    request = create_request(client, employee, project)
    login(manager)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})

    login(finance)
    future = (utcnow() + timedelta(days=400)).isoformat()
    response = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "card", "document": "ПП-2030", "paid_at": future},
    )
    assert response.status_code == 422
    assert "будущем" in response.json()["detail"]


def test_payment_before_decision_is_rejected(client, login, employee, manager, finance, project) -> None:
    login(employee)
    request = create_request(client, employee, project)
    login(manager)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})

    login(finance)
    earlier = (utcnow() - timedelta(days=3)).isoformat()
    response = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "card", "document": "ПП-РАНЬШЕ", "paid_at": earlier},
    )
    assert response.status_code == 422
    assert "раньше решения" in response.json()["detail"]


# --------------------------------------------------------------------------
# Разделение обязанностей
# --------------------------------------------------------------------------
def test_approver_cannot_pay(client, login, admin, employee, project) -> None:
    """У администратора есть оба права — и именно поэтому проверка нужна."""
    login(employee)
    request = create_request(client, employee, project)

    login(admin)
    decided = client.post(
        f"/api/requests/{request['id']}/decision", json={"approve": True}
    )
    assert decided.status_code == 200, decided.text

    response = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "card", "document": "ПП-САМ"},
    )
    assert response.status_code == 403
    assert "одобрили вы" in response.json()["detail"]


def test_someone_else_can_pay_what_admin_approved(
    client, login, admin, employee, finance, project
) -> None:
    login(employee)
    request = create_request(client, employee, project)
    login(admin)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})

    login(finance)
    paid = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "card", "document": "ПП-0007"},
    )
    assert paid.status_code == 200, paid.text


def test_nobody_pays_their_own_request(client, login, finance, admin, project, session) -> None:
    """Даже с правом на выплату свою заявку оплачивает кто-то другой."""
    login(finance)
    request = create_request(client, finance, project)
    login(admin)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})

    login(finance)
    response = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "cash", "document": "ПП-СЕБЕ"},
    )
    assert response.status_code == 403
    assert "собственной заявке" in response.json()["detail"]


def test_auto_approved_request_can_be_paid(client, login, employee, finance, project) -> None:
    """Автоодобрение выполняет система, а не человек: выплата не блокируется."""
    login(employee)
    request = create_request(client, employee, project, price="100.00")
    assert request["status"] == "approved"

    login(finance)
    paid = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "cash", "document": "ПП-МЕЛОЧЬ"},
    )
    assert paid.status_code == 200, paid.text


# --------------------------------------------------------------------------
# Черновик и отключённый объект
# --------------------------------------------------------------------------
def test_draft_cannot_move_to_disabled_project(client, login, admin, employee, project, session) -> None:
    from app.db.models import Project

    login(employee)
    draft = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Кисти", "quantity": 2, "price": "50.00"}],
            "submit": False,
        },
    ).json()

    closed = Project(name="Закрытый объект", active=False)
    session.add(closed)
    session.flush()

    response = client.patch(f"/api/requests/{draft['id']}", json={"project_id": closed.id})
    assert response.status_code == 422
    assert "отключён" in response.json()["detail"]
