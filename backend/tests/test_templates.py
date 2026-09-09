"""Шаблоны заявок: свои у каждого, применение не создаёт заявку."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import AuditLog, ExpenseRequest, Project, RequestTemplate
from app.services import templates as svc

LINES = [{"title": "Бензин АИ-92", "quantity": 40, "unit": "л"}]


def make(client, name="Заправка Opel", project_id=None, lines=None):
    body = {"name": name, "lines": lines or LINES}
    if project_id is not None:
        body["project_id"] = project_id
    return client.post("/api/templates", json=body)


# --- Свои и чужие --------------------------------------------------------------


def test_template_is_created_and_listed(client, login, employee, project) -> None:
    login(employee)
    created = make(client, project_id=project.id)
    assert created.status_code == 201

    body = created.json()
    assert body["name"] == "Заправка Opel"
    assert body["project_name"] == project.name
    assert body["lines"] == [{"title": "Бензин АИ-92", "quantity": 40, "unit": "л"}]
    assert body["usage_count"] == 0

    assert [t["id"] for t in client.get("/api/templates").json()] == [body["id"]]


def test_foreign_template_is_not_found(client, login, employee, manager) -> None:
    """Чужой шаблон — 404, как чужая заявка."""
    login(manager)
    other = make(client, name="Обед сотрудников").json()["id"]

    login(employee)
    assert client.get("/api/templates").json() == []
    assert client.patch(f"/api/templates/{other}", json={"name": "Моё"}).status_code == 404
    assert client.delete(f"/api/templates/{other}").status_code == 404
    assert client.post(f"/api/templates/{other}/apply").status_code == 404


def test_same_name_twice_is_refused(client, login, employee) -> None:
    login(employee)
    make(client)
    assert make(client).status_code == 409


def test_name_is_free_for_another_employee(client, login, employee, manager) -> None:
    login(employee)
    make(client)
    login(manager)
    assert make(client).status_code == 201


def test_empty_template_is_refused(client, login, employee) -> None:
    login(employee)
    assert client.post("/api/templates", json={"name": "Пустой", "lines": []}).status_code == 422


# --- Применение -----------------------------------------------------------------


def test_apply_counts_usage_and_creates_nothing(client, login, employee, project, session) -> None:
    """Подставить состав — не то же, что подать заявку."""
    login(employee)
    template_id = make(client, project_id=project.id).json()["id"]

    body = client.post(f"/api/templates/{template_id}/apply").json()
    assert body["warning"] is None
    assert body["template"]["usage_count"] == 1
    assert body["template"]["lines"][0]["title"] == "Бензин АИ-92"
    assert session.scalars(select(ExpenseRequest)).all() == []


def test_disabled_project_is_not_substituted(client, login, employee, project, session) -> None:
    """Шаблон нельзя применить с объектом, к которому нет доступа.

    Отключённый объект в заявку не подставляется: подать её всё равно не
    выйдет, а человек не поймёт почему.
    """
    login(employee)
    template_id = make(client, project_id=project.id).json()["id"]

    project.active = False
    session.commit()

    body = client.post(f"/api/templates/{template_id}/apply").json()
    assert "отключён" in body["warning"]
    assert body["template"]["project_id"] is None


def test_deleted_project_is_explained(client, login, employee, session) -> None:
    other = Project(name="Снесённый объект")
    session.add(other)
    session.commit()

    login(employee)
    template_id = make(client, project_id=other.id).json()["id"]
    session.delete(other)
    session.commit()

    body = client.post(f"/api/templates/{template_id}/apply").json()
    assert body["template"]["project_id"] is None


def test_most_used_go_first(client, login, employee) -> None:
    login(employee)
    rare = make(client, name="Такси").json()["id"]
    often = make(client, name="Обед сотрудников").json()["id"]
    for _ in range(3):
        client.post(f"/api/templates/{often}/apply")
    client.post(f"/api/templates/{rare}/apply")

    assert [t["id"] for t in client.get("/api/templates").json()] == [often, rare]


# --- Правка и удаление ----------------------------------------------------------


def test_project_can_be_cleared(client, login, employee, project) -> None:
    login(employee)
    template_id = make(client, project_id=project.id).json()["id"]

    body = client.patch(f"/api/templates/{template_id}", json={"clear_project": True}).json()
    assert body["project_id"] is None


def test_delete_removes_it(client, login, employee, session) -> None:
    login(employee)
    template_id = make(client).json()["id"]
    assert client.delete(f"/api/templates/{template_id}").status_code == 204
    assert session.scalars(select(RequestTemplate)).all() == []


def test_changes_go_to_the_audit_log(client, login, employee, session) -> None:
    login(employee)
    template_id = make(client).json()["id"]
    client.patch(f"/api/templates/{template_id}", json={"name": "Заправка"})
    client.delete(f"/api/templates/{template_id}")

    rows = session.scalars(select(AuditLog).where(AuditLog.entity == "template")).all()
    assert [r.action for r in rows] == [
        "template_created",
        "template_updated",
        "template_deleted",
    ]
    assert rows[0].username == employee.full_name


def test_limit_per_employee(client, login, employee) -> None:
    login(employee)
    for i in range(svc.MAX_PER_EMPLOYEE):
        assert make(client, name=f"Шаблон {i}").status_code == 201
    assert make(client, name="Ещё один").status_code == 409


def test_templates_require_login(client) -> None:
    assert client.get("/api/templates").status_code == 401
