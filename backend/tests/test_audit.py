"""Журнал действий: что в него попадает, кто его видит, как фильтруется."""

from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from tests.conftest import TEST_PASSWORD


@pytest.fixture
def as_admin(client, admin, login):
    login(admin)
    return client


def entries(client, **params) -> list[dict]:
    response = client.get("/api/audit", params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def actions(client, **params) -> list[str]:
    return [e["action"] for e in entries(client, **params)]


def test_journal_is_admin_only(client, login, manager, finance, employee) -> None:
    """Журнал показывает, кто когда входил, — это не для всех."""
    for person in (manager, finance, employee):
        login(person)
        assert client.get("/api/audit").status_code == 403


def test_successful_login_is_recorded(as_admin, admin) -> None:
    rows = entries(as_admin, action="login")
    assert rows, "вход администратора не попал в журнал"
    assert rows[0]["username"] == admin.full_name
    assert rows[0]["employee_id"] == admin.id
    # Адрес берётся из запроса: у TestClient он свой, но не пустой.
    assert rows[0]["ip"]


def test_failed_login_survives_rollback(client, employee, admin, login) -> None:
    """Неудачный вход завершается ошибкой, и вся транзакция откатывается.
    Запись журнала обязана уцелеть — иначе подбор пароля не виден."""
    response = client.post(
        "/api/auth/login", json={"email": employee.email, "password": "не тот пароль"}
    )
    assert response.status_code == 401

    login(admin)
    rows = entries(client, action="login_failed")
    assert len(rows) == 1
    assert rows[0]["employee_id"] == employee.id
    assert "попытка 1" in rows[0]["details"]


def test_unknown_email_does_not_fill_the_journal(client, admin, login) -> None:
    """Сканер, перебирающий адреса, не должен раздувать журнал.

    Администратора пускаем в систему заранее: неудачный вход завершается
    ошибкой, и откат транзакции унёс бы ещё не сохранённые данные теста.
    """
    login(admin)
    client.post(
        "/api/auth/login", json={"email": "нет-такого@it-hona.tj", "password": "x"}
    )
    assert actions(client, action="login_failed") == []


def test_logout_is_recorded(client, employee, admin, login) -> None:
    login(employee)
    assert client.post("/api/auth/logout").status_code == 204

    login(admin)
    rows = entries(client, action="logout")
    assert len(rows) == 1
    assert rows[0]["employee_id"] == employee.id


def test_logout_without_session_is_quiet(client, admin, login) -> None:
    """Выход с истёкшей сессией чистит cookie и молчит в журнале."""
    assert client.post("/api/auth/logout").status_code == 204
    login(admin)
    assert actions(client, action="logout") == []


def test_reference_change_records_who_did_it(as_admin, admin) -> None:
    """Имя действующего сотрудника подставляется само — из контекста запроса."""
    created = as_admin.post("/api/projects", json={"name": "Объект журнала"})
    assert created.status_code == 201, created.text

    rows = entries(as_admin, entity="project", action="create")
    assert len(rows) == 1
    assert rows[0]["username"] == admin.full_name
    assert rows[0]["employee_id"] == admin.id
    assert rows[0]["entity_id"] == str(created.json()["id"])


def test_request_actions_visible_to_admin(
    client, login, employee, manager, procurement, admin, project, pipeline
) -> None:
    """Весь путь заявки виден в журнале: подача, закуп, оценка, решение."""
    login(employee)
    created = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Плинтус", "quantity": 10, "unit": "шт."}],
        },
    )
    request_id = created.json()["id"]
    number = created.json()["number"]
    pipeline(request_id, manager=manager, buyer=procurement)

    login(admin)
    rows = entries(client, entity="request")
    by_action = {r["action"]: r for r in rows}
    for action in ("create", "submit", "sourcing", "priced", "approve"):
        assert action in by_action, f"в журнале нет действия {action}"
    assert by_action["create"]["username"] == employee.full_name
    assert by_action["sourcing"]["username"] == manager.full_name
    assert by_action["priced"]["username"] == procurement.full_name
    assert by_action["approve"]["username"] == manager.full_name
    assert by_action["approve"]["entity_id"] == number


def test_filters_and_paging(as_admin, admin, employee) -> None:
    for i in range(3):
        as_admin.post("/api/projects", json={"name": f"Объект {i}"})

    page = as_admin.get("/api/audit", params={"entity": "project", "limit": 2}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    # Сверху — самое свежее.
    times = [row["created_at"] for row in page["items"]]
    assert times == sorted(times, reverse=True)

    second = as_admin.get(
        "/api/audit", params={"entity": "project", "limit": 2, "offset": 2}
    ).json()
    assert len(second["items"]) == 1

    assert entries(as_admin, employee_id=employee.id) == []
    assert entries(as_admin, search="Объект 1")


def test_date_filter_covers_the_whole_local_day(as_admin) -> None:
    """«По сегодня» включает сегодняшние записи целиком, а не до полуночи UTC."""
    from app.core.time import local_date, utcnow

    today = local_date(utcnow()).isoformat()
    rows = entries(as_admin, date_from=today, date_to=today)
    assert rows, "сегодняшний вход не попал в диапазон «с сегодня по сегодня»"


def test_actors_list_for_filter(as_admin, admin) -> None:
    names = [a["username"] for a in as_admin.get("/api/audit/actors").json()]
    assert admin.full_name in names


def test_journal_cannot_be_edited(as_admin) -> None:
    """Записи журнала не правятся и не удаляются — методов просто нет."""
    assert as_admin.post("/api/audit", json={}).status_code == 405
    # Метода нет вовсе — маршрут не объявлен.
    assert as_admin.delete("/api/audit/1").status_code in (404, 405)


def test_excel_export(as_admin) -> None:
    response = as_admin.get("/api/exports/audit.xlsx")
    assert response.status_code == 200, response.text
    assert "spreadsheetml" in response.headers["content-type"]

    wb = load_workbook(io.BytesIO(response.content))
    ws = wb.active
    assert ws.title == "Журнал"
    header = [c.value for c in ws[4]]
    assert "Сотрудник" in header and "Действие" in header
    # Первая строка данных — понятная подпись, а не код действия.
    assert any(
        row[3].value == "Вход в систему"
        for row in ws.iter_rows(min_row=5)
        if row[3].value
    )


def test_export_is_admin_only(client, login, finance) -> None:
    login(finance)
    assert client.get("/api/exports/audit.xlsx").status_code == 403


def test_password_change_is_distinct_from_admin_reset(client, login, employee, admin) -> None:
    login(employee)
    changed = client.post(
        "/api/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "новый-длинный-пароль"},
    )
    assert changed.status_code == 200, changed.text

    login(admin)
    assert actions(client, action="password_changed")
    assert actions(client, action="set_password") == []
