"""Разграничение прав: кто что видит и что может делать.

Эти тесты — граница безопасности системы. Каждый проверяет, что попытка
выйти за пределы роли отклоняется сервером, а не только скрыта в панели.
"""

from __future__ import annotations

import pytest

from app.core.permissions import Permission, has_permission, permissions_for
from app.db.models import EmployeeRole

LINES = [{"title": "Материалы", "quantity": 1, "price": "2000.00"}]
CHEAP = [{"title": "Обед", "quantity": 1, "price": "30.00"}]


def submit(client, employee, project, lines=None) -> dict:
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": lines or LINES,
            "submit": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Матрица прав
# --------------------------------------------------------------------------
def test_employee_has_only_own_requests() -> None:
    perms = permissions_for(EmployeeRole.EMPLOYEE)
    assert Permission.CREATE_REQUEST in perms
    assert Permission.VIEW_ALL_REQUESTS not in perms
    assert Permission.DECIDE_REQUEST not in perms
    assert Permission.PAY_REQUEST not in perms


def test_manager_decides_but_does_not_pay() -> None:
    perms = permissions_for(EmployeeRole.MANAGER)
    assert Permission.DECIDE_REQUEST in perms
    assert Permission.PAY_REQUEST not in perms
    assert Permission.MANAGE_REFERENCE not in perms


def test_finance_pays_but_does_not_decide() -> None:
    """Разделение обязанностей: кто согласовал, тот не платит."""
    perms = permissions_for(EmployeeRole.FINANCE)
    assert Permission.PAY_REQUEST in perms
    assert Permission.DECIDE_REQUEST not in perms


def test_admin_has_everything() -> None:
    assert permissions_for(EmployeeRole.ADMIN) == frozenset(Permission)


def test_unknown_role_gets_nothing() -> None:
    """Значение из будущей версии не должно давать прав по умолчанию."""
    assert permissions_for("нет такой роли") == frozenset()  # type: ignore[arg-type]
    assert not has_permission("нет такой роли", Permission.DECIDE_REQUEST)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Доступ без входа
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/requests"),
        ("get", "/api/employees"),
        ("get", "/api/projects"),
        ("get", "/api/team"),
        ("get", "/api/reports/dashboard"),
        ("get", "/api/reports/budget"),
        ("get", "/api/auth/me"),
        ("post", "/api/projects"),
    ],
)
def test_anonymous_is_rejected(client, method, path) -> None:
    assert getattr(client, method)(path).status_code == 401


def test_health_stays_open(client) -> None:
    """Docker опрашивает /health без учётных данных."""
    assert client.get("/health").status_code == 200


# --------------------------------------------------------------------------
# Видимость чужих заявок
# --------------------------------------------------------------------------
def test_employee_sees_only_own_requests(
    client, login, employee, manager, project
) -> None:
    login(manager)
    submit(client, manager, project)
    login(employee)
    submit(client, employee, project)

    body = client.get("/api/requests", params={"all_periods": True}).json()
    assert body["total"] == 1
    assert {i["employee_name"] for i in body["items"]} == {employee.full_name}


def test_employee_cannot_widen_filter(client, login, employee, manager, project) -> None:
    """Фильтр по автору навязывает сервер: подмена в адресной строке не работает."""
    login(manager)
    submit(client, manager, project)
    login(employee)

    body = client.get(
        "/api/requests", params={"employee_id": manager.id, "all_periods": True}
    ).json()
    assert body["total"] == 0


def test_foreign_request_is_404_not_403(
    client, login, employee, manager, project
) -> None:
    """404, а не 403: иначе по коду ответа можно перебрать чужие номера."""
    login(manager)
    foreign = submit(client, manager, project)
    login(employee)
    assert client.get(f"/api/requests/{foreign['id']}").status_code == 404


def test_manager_sees_all(client, login, employee, manager, project) -> None:
    login(employee)
    submit(client, employee, project)
    login(manager)
    submit(client, manager, project)

    body = client.get("/api/requests", params={"all_periods": True}).json()
    assert body["total"] == 2


# --------------------------------------------------------------------------
# Действия
# --------------------------------------------------------------------------
def test_employee_cannot_decide(client, login, employee, manager, project) -> None:
    login(manager)
    foreign = submit(client, manager, project)
    login(employee)
    response = client.post(
        f"/api/requests/{foreign['id']}/decision", json={"approve": True}
    )
    assert response.status_code in (403, 404)


def test_finance_cannot_decide(client, login, employee, finance, project) -> None:
    login(employee)
    request = submit(client, employee, project)
    login(finance)
    assert (
        client.post(
            f"/api/requests/{request['id']}/decision", json={"approve": True}
        ).status_code
        == 403
    )


def test_manager_cannot_pay(client, login, employee, manager, project) -> None:
    login(employee)
    request = submit(client, employee, project)
    login(manager)
    client.post(f"/api/requests/{request['id']}/decision", json={"approve": True})
    response = client.post(
        f"/api/requests/{request['id']}/payment",
        json={"method": "card", "document": "ПП-0001"},
    )
    assert response.status_code == 403


def test_manager_cannot_approve_own_request(client, login, manager, project) -> None:
    """Собственную заявку не согласуют даже с правом решения."""
    login(manager)
    own = submit(client, manager, project)
    response = client.post(
        f"/api/requests/{own['id']}/decision", json={"approve": True}
    )
    assert response.status_code == 403


def test_employee_cannot_submit_for_others(
    client, login, employee, manager, project
) -> None:
    login(employee)
    response = client.post(
        "/api/requests",
        json={"employee_id": manager.id, "project_id": project.id, "lines": LINES},
    )
    assert response.status_code == 403


def test_manager_cannot_submit_for_others(
    client, login, employee, manager, project
) -> None:
    """Даже руководитель не подаёт заявки за подчинённых: автор должен быть
    настоящим, иначе непонятно, чей это расход."""
    login(manager)
    response = client.post(
        "/api/requests",
        json={"employee_id": employee.id, "project_id": project.id, "lines": LINES},
    )
    assert response.status_code == 403


def test_admin_can_submit_for_others(client, login, admin, employee, project) -> None:
    login(admin)
    response = client.post(
        "/api/requests",
        json={"employee_id": employee.id, "project_id": project.id, "lines": LINES},
    )
    assert response.status_code == 201
    assert response.json()["employee_id"] == employee.id


def test_employee_cannot_delete_foreign_draft(
    client, login, employee, manager, project
) -> None:
    login(manager)
    draft = client.post(
        "/api/requests",
        json={
            "employee_id": manager.id,
            "project_id": project.id,
            "lines": LINES,
            "submit": False,
        },
    ).json()
    login(employee)
    assert client.delete(f"/api/requests/{draft['id']}").status_code == 404


# --------------------------------------------------------------------------
# Справочники и отчёты
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role_fixture", ["employee", "manager", "finance"])
def test_only_admin_manages_reference(client, login, request, role_fixture) -> None:
    person = request.getfixturevalue(role_fixture)
    login(person)
    assert client.post("/api/projects", json={"name": "Новый объект"}).status_code == 403


def test_admin_manages_reference(client, login, admin) -> None:
    login(admin)
    assert client.post("/api/projects", json={"name": "Новый объект"}).status_code == 201


def test_employee_cannot_see_reports(client, login, employee) -> None:
    login(employee)
    for path in ("/api/reports/dashboard", "/api/reports/budget", "/api/team"):
        assert client.get(path).status_code == 403, path


@pytest.mark.parametrize("role_fixture", ["manager", "finance", "admin"])
def test_reports_open_to_manager_finance_admin(
    client, login, request, role_fixture
) -> None:
    login(request.getfixturevalue(role_fixture))
    assert client.get("/api/reports/dashboard").status_code == 200


def test_everyone_reads_reference(client, login, employee, project) -> None:
    """Справочники нужны всем: без них не заполнить заявку."""
    login(employee)
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/employees").status_code == 200


def test_overview_for_employee_has_no_queue(client, login, employee, manager, project) -> None:
    """Дашборд открыт всем вошедшим, но очередь решений — только тем, кто решает,
    а цифры сотрудника — только по его заявкам."""
    login(manager)
    submit(client, manager, project)
    login(employee)
    submit(client, employee, project)

    body = client.get("/api/requests/overview").json()
    assert body["decisions"] == 0 and body["queue"] == []
    assert body["in_work"] == 1

    login(manager)
    body = client.get("/api/requests/overview").json()
    assert body["in_work"] == 2
    # Своя заявка в очередь руководителя не попадает.
    assert body["decisions"] == 1
    assert body["queue"][0]["employee_name"] == employee.full_name


def test_every_foreign_key_has_an_index() -> None:
    """Ссылка на другую таблицу без индекса — перебор всей таблицы.

    Проверяется по модели, а не по базе: так забытый индекс виден до
    выката, а не после того, как отчёт по объекту начал думать секунду.
    """
    from app.db.models import Base

    from sqlalchemy import UniqueConstraint

    missing = []
    for table in Base.metadata.tables.values():
        # Индекс покрывает колонку, если она в нём первая: по остальным
        # позициям составного индекса поиск не идёт.
        leading = {next(iter(i.columns)).name for i in table.indexes if len(i.columns)}
        # Уникальное ограничение — это тоже индекс, PostgreSQL строит его
        # сам. И на уровне колонки (`unique=True`), и в `__table_args__`.
        leading |= {c.name for c in table.columns if c.unique}
        leading |= {
            next(iter(c.columns)).name
            for c in table.constraints
            if isinstance(c, UniqueConstraint) and len(c.columns)
        }
        if table.primary_key:
            leading |= {next(iter(table.primary_key.columns)).name}

        for fk in table.foreign_keys:
            if fk.parent.name not in leading:
                missing.append(f"{table.name}.{fk.parent.name}")

    assert not missing, "внешние ключи без индекса: " + ", ".join(sorted(missing))
