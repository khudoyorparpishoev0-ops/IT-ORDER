"""Экран «Сотрудники»: состояние доступа и защита от потери администратора."""

from __future__ import annotations

import pytest

from app.db.models import EmployeeRole
from tests.conftest import TEST_PASSWORD, make_employee


def access_row(client, employee_id: int) -> dict:
    response = client.get("/api/employees/access")
    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()}
    return rows[employee_id]


@pytest.fixture
def as_admin(client, admin, login):
    login(admin)
    return client


def test_access_is_admin_only(client, login, manager, employee) -> None:
    """Кто и когда входил, у кого нет второго фактора — не дело коллег."""
    login(manager)
    assert client.get("/api/employees/access").status_code == 403
    login(employee)
    assert client.get("/api/employees/access").status_code == 403


def test_access_path_is_not_read_as_id(as_admin, admin) -> None:
    """«access» не должен разбираться как номер сотрудника: иначе 422."""
    response = as_admin.get("/api/employees/access")
    assert response.status_code == 200
    assert admin.id in {row["id"] for row in response.json()}


def test_new_employee_cannot_sign_in_until_password_is_set(as_admin) -> None:
    created = as_admin.post(
        "/api/employees",
        json={"full_name": "Далер Сафаров", "email": "d.safarov@it-hona.tj"},
    )
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]

    row = access_row(as_admin, new_id)
    assert row["has_password"] is False
    assert row["can_sign_in"] is False
    assert row["last_login_at"] is None

    set_password = as_admin.put(
        f"/api/employees/{new_id}/password", json={"password": "пароль-подлиннее"}
    )
    assert set_password.status_code == 200, set_password.text

    row = access_row(as_admin, new_id)
    assert row["has_password"] is True
    assert row["can_sign_in"] is True


def test_access_shows_second_factor_state(as_admin, admin, finance, employee) -> None:
    rows = {row["id"]: row for row in as_admin.get("/api/employees/access").json()}
    # Фикстура login проходит обязательную настройку второго фактора,
    # поэтому у администратора он уже включён.
    assert rows[admin.id]["two_factor_enabled"] is True
    assert rows[admin.id]["two_factor_required"] is True
    # Финансам он обязателен, но эта запись ещё ни разу не входила.
    assert rows[finance.id]["two_factor_enabled"] is False
    assert rows[finance.id]["two_factor_required"] is True
    assert rows[employee.id]["two_factor_required"] is False


def test_employee_without_password_is_not_locked_out_by_login_attempt(
    as_admin, session
) -> None:
    """Пустой пароль не должен считаться неудачной попыткой входа."""
    person = make_employee(
        session, full_name="Без пароля", email="no.pass@it-hona.tj", password_hash=None
    )
    session.flush()
    row = access_row(as_admin, person.id)
    assert row["can_sign_in"] is False
    assert row["locked_until"] is None


def test_last_admin_cannot_lose_rights(as_admin, admin) -> None:
    """Иначе справочники, роли и пароли не сможет менять никто."""
    demote = as_admin.patch(f"/api/employees/{admin.id}", json={"role": "employee"})
    assert demote.status_code == 409
    assert "администратор" in demote.json()["detail"].lower()

    disable = as_admin.patch(f"/api/employees/{admin.id}", json={"active": False})
    assert disable.status_code == 409

    removed = as_admin.delete(f"/api/employees/{admin.id}")
    assert removed.status_code == 409


def test_second_admin_makes_the_first_replaceable(as_admin, admin, session) -> None:
    make_employee(
        session,
        full_name="Второй администратор",
        email="admin2@it-hona.tj",
        role=EmployeeRole.ADMIN,
    )
    session.flush()

    demote = as_admin.patch(f"/api/employees/{admin.id}", json={"role": "employee"})
    assert demote.status_code == 200, demote.text
    assert demote.json()["role"] == "employee"


def test_disabled_admin_does_not_count_as_the_last_one(as_admin, admin, session) -> None:
    """Отключённая запись прав не даёт, поэтому и заменой не считается."""
    make_employee(
        session,
        full_name="Уволенный администратор",
        email="ex.admin@it-hona.tj",
        role=EmployeeRole.ADMIN,
        active=False,
    )
    session.flush()

    response = as_admin.patch(f"/api/employees/{admin.id}", json={"role": "manager"})
    assert response.status_code == 409


def test_admin_password_change_takes_effect(as_admin, employee, client, session) -> None:
    """Назначенный администратором пароль действительно пускает в систему."""
    new_password = "новый-пароль-сотрудника"
    assert (
        as_admin.put(
            f"/api/employees/{employee.id}/password", json={"password": new_password}
        ).status_code
        == 200
    )
    client.post("/api/auth/logout")

    old = client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert old.status_code == 401

    fresh = client.post(
        "/api/auth/login", json={"email": employee.email, "password": new_password}
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["status"] == "ok"
