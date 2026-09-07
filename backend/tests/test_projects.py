"""Справочник объектов: заведение, правка, счётчики и права."""

from __future__ import annotations

import pytest


@pytest.fixture
def as_admin(client, admin, login):
    login(admin)
    return client


def test_only_admin_creates_projects(client, login, manager, employee) -> None:
    for person in (manager, employee):
        login(person)
        assert client.post("/api/projects", json={"name": "Чужой"}).status_code == 403


def test_everyone_reads_projects(client, login, employee, project) -> None:
    """Список нужен, чтобы заполнить заявку, — читают все вошедшие."""
    login(employee)
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == [project.name]


def test_create_and_rename(as_admin) -> None:
    created = as_admin.post("/api/projects", json={"name": "Рекова 132"})
    assert created.status_code == 201, created.text
    assert created.json()["requests_count"] == 0

    renamed = as_admin.patch(
        f"/api/projects/{created.json()['id']}", json={"name": "Рекова 132 · корпус Б"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Рекова 132 · корпус Б"


def test_duplicate_name_is_409(as_admin, project) -> None:
    assert as_admin.post("/api/projects", json={"name": project.name}).status_code == 409


def test_disabled_project_is_not_offered_but_stays(as_admin, project) -> None:
    disabled = as_admin.patch(f"/api/projects/{project.id}", json={"active": False})
    assert disabled.status_code == 200
    assert disabled.json()["active"] is False

    only_active = as_admin.get("/api/projects", params={"only_active": True}).json()
    assert only_active == []
    assert len(as_admin.get("/api/projects").json()) == 1


def test_counters_show_work_on_the_project(
    client, login, employee, manager, admin, project
) -> None:
    login(employee)
    for price in ("1500.00", "200.00"):
        created = client.post(
            "/api/requests",
            json={
                "employee_id": employee.id,
                "project_id": project.id,
                "lines": [{"title": "Материалы", "quantity": 1, "price": price}],
            },
        )
        assert created.status_code == 201, created.text

    login(admin)
    row = next(p for p in client.get("/api/projects").json() if p["id"] == project.id)
    assert row["requests_count"] == 2
    # 1500 ждёт решения, 200 одобрены автоматически — расход считаем по обеим.
    assert row["spent"] == "1700.00"


def test_draft_counts_but_does_not_spend(client, login, employee, admin, project) -> None:
    login(employee)
    client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Черновик", "quantity": 1, "price": "900.00"}],
            "submit": False,
        },
    )
    login(admin)
    row = next(p for p in client.get("/api/projects").json() if p["id"] == project.id)
    assert row["requests_count"] == 1
    assert row["spent"] == "0.00"


def test_project_deletion_is_not_offered(as_admin, project) -> None:
    """Удаления объектов нет: заявки должны сохранить, на что был расход."""
    assert as_admin.delete(f"/api/projects/{project.id}").status_code in (404, 405)
