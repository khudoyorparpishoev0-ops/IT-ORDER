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


# --- Помощник по материалам ---------------------------------------------------


def advice(client, title: str, unit: str | None = None) -> dict:
    response = client.post("/api/materials/advice", json={"title": title, "unit": unit})
    assert response.status_code == 200, response.text
    return response.json()


def test_assistant_is_off_without_key(as_employee) -> None:
    """Без ключа помощник выключен, а форма работает как раньше."""
    status = as_employee.get("/api/materials/assistant").json()
    assert status == {"enabled": False, "model": None}
    from app.core import assistant

    assistant.set_transport(None)
    body = advice(as_employee, "гофра16")
    assert body["enabled"] is False and body["available"] is False


def test_assistant_fixes_spelling_and_units(as_employee, assistant_box) -> None:
    assistant_box.answer = {
        "normalized": "Гофра 16 мм",
        "unit": "м",
        "matches_existing": False,
        "notes": ["Укажите цвет и тип: ПВХ или металл"],
    }
    body = advice(as_employee, "гофра16")
    assert body["enabled"] and body["available"]
    assert body["suggested"] == "Гофра 16 мм"
    assert body["changed"] is True
    assert body["unit"] == "м"
    assert body["notes"] == ["Укажите цвет и тип: ПВХ или металл"]


def test_assistant_sees_the_catalog(as_employee, employee, project, assistant_box) -> None:
    """Модель получает то, что уже заказывали, — иначе ей не знать, как
    материал называют в компании."""
    need(as_employee, employee, project, [{"title": "Гофра гибкая 16 мм", "quantity": 1, "unit": "м"}])
    assistant_box.answer = {
        "normalized": "Гофра гибкая 16 мм",
        "unit": "м",
        "matches_existing": True,
        "notes": [],
    }
    body = advice(as_employee, "гофра16")
    assert "Гофра гибкая 16 мм (м)" in assistant_box.prompts[-1]
    assert body["matches_existing"] is True
    assert body["suggested"] == "Гофра гибкая 16 мм"


def test_assistant_answers_are_cached(as_employee, assistant_box) -> None:
    """Одно и то же слово спрашивают десятки раз в день: платить за
    каждый раз незачем."""
    assistant_box.answer = {"normalized": "Кабель UTP", "unit": "м", "matches_existing": False, "notes": []}
    advice(as_employee, "кабель utp")
    advice(as_employee, "Кабель UTP ")
    assert len(assistant_box.prompts) == 1


def test_assistant_failure_is_not_an_error(as_employee, assistant_box) -> None:
    """Модель не ответила — форма получает available=false, а не 500."""
    body = advice(as_employee, "гофра16")
    assert body["enabled"] is True and body["available"] is False
    assert body["suggested"] is None


def test_assistant_keeps_correct_spelling(as_employee, assistant_box) -> None:
    assistant_box.answer = {"normalized": "Кабель UTP Cat6", "unit": None, "matches_existing": False, "notes": []}
    body = advice(as_employee, "Кабель UTP Cat6")
    assert body["changed"] is False


def test_short_titles_are_not_sent(as_employee, assistant_box) -> None:
    body = advice(as_employee, "ла")
    assert assistant_box.prompts == [] and body["suggested"] is None


def test_advice_requires_login(client) -> None:
    assert client.post("/api/materials/advice", json={"title": "гофра"}).status_code == 401
