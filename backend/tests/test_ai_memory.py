"""Память ORDER: подсказки из истории заявок, дубли, алиасы.

Главное свойство, которое проверяется здесь: всё это работает БЕЗ модели.
Помощник выключен в этих тестах (автоиспользуемая фикстура), а подсказки
всё равно приходят — потому что считает их база, а не Claude.
"""

from __future__ import annotations

import pytest

from app.db.models import MaterialAlias
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import ai_memory
from app.services import requests as svc
from app.services.material_norm import normalize
from app.services.reference import materials_catalog


def submit(session, employee, project, *titles, unit="шт."):
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title=t, quantity=1, unit=unit) for t in titles],
            submit=True,
        ),
    )
    session.commit()
    return request


# --- Нормализация -------------------------------------------------------------


@pytest.mark.parametrize(
    "wrote, expected",
    [
        ("гофра16", "гофра 16"),
        ("Гофра 16мм", "гофра 16 мм"),
        ("ГОФРА 16 ММ.", "гофра 16 мм"),
        ("Кабель UTP Cat6", "кабель utp cat 6"),
        ("кабель  utp   cat 6", "кабель utp cat 6"),
        ("Ёлка", "елка"),
        ("Плитка м²", "плитка м 2"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize(wrote, expected) -> None:
    assert normalize(wrote) == expected


def test_line_keeps_both_spellings(session, employee, project) -> None:
    """Показываем то, что написал человек; ищем по приведённому."""
    request = submit(session, employee, project, "ГОФРА 16 ММ.")
    line = request.lines[0]
    assert line.title == "ГОФРА 16 ММ."
    assert line.normalized_text == "гофра 16 мм"


# --- Подсказки из истории ------------------------------------------------------


def test_frequent_counts_by_normalized_spelling(session, employee, project) -> None:
    """«гофра16» и «Гофра 16 мм» — один материал, а не два."""
    submit(session, employee, project, "Гофра 16 мм")
    submit(session, employee, project, "гофра 16мм")
    submit(session, employee, project, "Хомут 300")

    top = ai_memory.frequent(session)
    assert [(x.title, x.times) for x in top][0] == ("гофра 16мм", 2)
    assert len(top) == 2


def test_frequent_shows_the_freshest_spelling(session, employee, project) -> None:
    """Подсказка не должна тянуть за собой старую опечатку."""
    submit(session, employee, project, "гофра16")
    submit(session, employee, project, "Гофра 16")

    assert ai_memory.frequent(session)[0].title == "Гофра 16"


def test_draft_is_not_a_need_yet(session, employee, project) -> None:
    """Черновик правят и удаляют — в памяти ему не место."""
    svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Черновая позиция", quantity=1, unit="шт.")],
            submit=False,
        ),
    )
    session.commit()
    assert ai_memory.frequent(session) == []


def test_mine_is_only_mine(session, employee, manager, project) -> None:
    submit(session, employee, project, "Кабель UTP Cat6")
    submit(session, manager, project, "Бетон М300")

    assert [x.title for x in ai_memory.mine(session, employee.id)] == ["Кабель UTP Cat6"]
    assert [x.title for x in ai_memory.mine(session, manager.id)] == ["Бетон М300"]


def test_project_history(session, employee, project) -> None:
    from app.db.models import Project

    other = Project(name="Речная набережная")
    session.add(other)
    session.flush()

    submit(session, employee, project, "Песок речной")
    submit(session, employee, other, "Цемент М500")

    assert [x.title for x in ai_memory.by_project(session, project.id)] == ["Песок речной"]
    assert [x.title for x in ai_memory.by_project(session, other.id)] == ["Цемент М500"]


def test_suggestion_is_checkable(session, employee, project) -> None:
    """У подсказки есть номер и дата заявки: она должна быть проверяемой."""
    request = submit(session, employee, project, "Хомут 300 мм")
    (item,) = ai_memory.frequent(session)
    assert item.last_number == request.number
    assert item.last_date == request.created_at.date().isoformat()


# --- Повторы -------------------------------------------------------------------


def test_duplicate_is_found_by_normalized_spelling(session, employee, project) -> None:
    """Один написал «гофра16», другой «Гофра 16 мм» — потребность одна."""
    first = submit(session, employee, project, "гофра16")

    found = ai_memory.similar_requests(session, titles=["Гофра 16"], project_id=project.id)
    assert [r.number for r in found] == [first.number]
    assert found[0].materials == ["гофра16"]


def test_different_material_is_not_a_duplicate(session, employee, project) -> None:
    submit(session, employee, project, "Гофра 16 мм")
    assert ai_memory.similar_requests(session, titles=["Бетон М300"]) == []


def test_empty_titles_find_nothing(session, employee, project) -> None:
    submit(session, employee, project, "Гофра 16 мм")
    assert ai_memory.similar_requests(session, titles=["", "   "]) == []


def test_duplicates_respect_visibility(client, login, employee, manager, project, session) -> None:
    """Сотрудник видит только свои повторы: чужая заявка — чужая заявка."""
    submit(session, manager, project, "Гофра 16 мм")
    ask = {"titles": ["гофра16мм"], "project_id": project.id}

    login(employee)
    assert client.post("/api/assistant/duplicates", json=ask).json()["requests"] == []

    login(manager)
    body = client.post("/api/assistant/duplicates", json=ask).json()
    assert [r["number"] for r in body["requests"]] == ["РЗ-0001"]
    assert body["days"] == ai_memory.DUPLICATE_DAYS


# --- Работа без модели ----------------------------------------------------------


def test_memory_works_without_the_model(client, login, employee, project, session) -> None:
    """Ключа нет, помощник молчит — подсказки на месте."""
    submit(session, employee, project, "Кабель UTP Cat6")

    login(employee)
    body = client.get(f"/api/assistant/memory?project_id={project.id}").json()
    assert [x["title"] for x in body["frequent"]] == ["Кабель UTP Cat6"]
    assert [x["title"] for x in body["mine"]] == ["Кабель UTP Cat6"]
    assert [x["title"] for x in body["project"]] == ["Кабель UTP Cat6"]


def test_memory_requires_login(client) -> None:
    assert client.get("/api/assistant/memory").status_code == 401
    assert client.post("/api/assistant/duplicates", json={"titles": []}).status_code == 401


def test_memory_of_another_employee_is_not_exposed(
    client, login, employee, manager, project, session
) -> None:
    """«Своё» — это своё: чужая личная история в подсказки не попадает."""
    submit(session, manager, project, "Личный материал руководителя")

    login(employee)
    body = client.get("/api/assistant/memory").json()
    assert body["mine"] == []
    # Названия материалов при этом общие: иначе новый сотрудник не получил
    # бы ни одной подсказки в первый день.
    assert [x["title"] for x in body["frequent"]] == ["Личный материал руководителя"]


# --- Алиасы: поправки, принятые людьми -----------------------------------------


def test_applied_correction_becomes_an_alias(client, login, employee, session, assistant_box) -> None:
    assistant_box.answer = {
        "normalized": "Гофра гибкая 16 мм",
        "unit": "м",
        "matches_existing": False,
        "notes": [],
    }
    login(employee)
    advice = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    client.post(f"/api/ai/applied/{advice['interaction_id']}")

    alias = ai_memory.alias_for(session, "ГОФРА16")
    assert alias is not None
    assert alias.canonical == "Гофра гибкая 16 мм"
    assert alias.uses == 1


def test_known_alias_answers_without_the_model(
    client, login, employee, session, assistant_box
) -> None:
    """Такую поправку люди уже приняли — платить за неё второй раз не за что."""
    session.add(MaterialAlias(alias="гофра 16", canonical="Гофра гибкая 16 мм", unit="м", uses=1))
    session.commit()

    login(employee)
    body = client.post("/api/materials/advice", json={"title": "гофра16"}).json()

    assert body["suggested"] == "Гофра гибкая 16 мм"
    assert body["matches_existing"] is True
    assert body["unit"] == "м"
    assert assistant_box.prompts == [], "к модели не ходили"


def test_alias_is_not_remembered_when_nothing_changed(session) -> None:
    ai_memory.remember_alias(session, wrote="Гофра 16 мм", canonical="гофра 16мм", unit=None)
    session.flush()
    assert ai_memory.alias_for(session, "Гофра 16 мм") is None


def test_repeated_correction_counts_up(session) -> None:
    for _ in range(3):
        ai_memory.remember_alias(session, wrote="гофра16", canonical="Гофра 16 мм", unit="м")
        session.flush()
    alias = ai_memory.alias_for(session, "гофра16")
    assert alias.uses == 3


# --- Каталог -------------------------------------------------------------------


def test_catalog_collapses_spellings(session, employee, project) -> None:
    submit(session, employee, project, "Гофра 16 мм")
    submit(session, employee, project, "гофра16мм")

    catalog = materials_catalog(session)
    assert [(title, uses) for title, _, uses in catalog] == [("гофра16мм", 2)]


def test_catalog_search_finds_by_normalized_spelling(session, employee, project) -> None:
    """«гофра16» должно находить «Гофра 16 мм», хотя такой строки нет."""
    submit(session, employee, project, "Гофра 16 мм")
    assert [t for t, _, _ in materials_catalog(session, search="гофра16")] == ["Гофра 16 мм"]
