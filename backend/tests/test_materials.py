"""Подсказки материалов: собираются из заявок, а не из отдельного справочника."""

from __future__ import annotations

import pytest


def need(client, employee, project, lines) -> dict:
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": lines,
            "submit": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def as_employee(client, employee, login):
    login(employee)
    return client


def titles(client, **params) -> list[str]:
    response = client.get("/api/materials", params=params)
    assert response.status_code == 200, response.text
    return [m["title"] for m in response.json()]


def test_suggestions_come_from_past_requests(as_employee, employee, project) -> None:
    need(
        as_employee,
        employee,
        project,
        [
            {"title": "Хомут 20", "quantity": 5, "unit": "шт."},
            {"title": "Цемент М400", "quantity": 2, "unit": "мешок"},
        ],
    )
    assert set(titles(as_employee)) == {"Хомут 20", "Цемент М400"}


def test_frequent_materials_come_first(as_employee, employee, project) -> None:
    for _ in range(3):
        need(as_employee, employee, project, [{"title": "Цемент М400", "quantity": 1}])
    need(as_employee, employee, project, [{"title": "Редкая позиция", "quantity": 1}])

    assert titles(as_employee)[0] == "Цемент М400"


def test_spelling_variants_collapse_to_the_latest(as_employee, employee, project) -> None:
    """«хомут» и «Хомут» — одно и то же. Показываем свежее написание,
    иначе подсказка тянула бы за собой старую опечатку."""
    need(as_employee, employee, project, [{"title": "хомут", "quantity": 1}])
    need(as_employee, employee, project, [{"title": "Хомут", "quantity": 1}])

    found = titles(as_employee)
    assert found == ["Хомут"]


def test_unit_comes_from_the_latest_use(as_employee, employee, project) -> None:
    need(as_employee, employee, project, [{"title": "Плёнка", "quantity": 1, "unit": "рулон"}])
    materials = as_employee.get("/api/materials").json()
    assert materials[0]["unit"] == "рулон"
    assert materials[0]["uses"] == 1


def test_search_filters_suggestions(as_employee, employee, project) -> None:
    need(
        as_employee,
        employee,
        project,
        [
            {"title": "Цемент М400", "quantity": 1},
            {"title": "Кабель ВВГ", "quantity": 1},
        ],
    )
    assert titles(as_employee, search="цем") == ["Цемент М400"]
    assert titles(as_employee, search="ввг") == ["Кабель ВВГ"]
    assert titles(as_employee, search="нет такого") == []


def test_suggestions_require_login(client) -> None:
    assert client.get("/api/materials").status_code == 401


def test_empty_catalog_is_not_an_error(as_employee) -> None:
    assert titles(as_employee) == []
