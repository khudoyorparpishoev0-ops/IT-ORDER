"""Журнал обращений к AI: что пишем, чего не пишем и кто это видит."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AiInteraction, AiKind, RequestStatus
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import ai_log
from app.services import requests as svc

ADVICE = {
    "normalized": "Гофра гибкая 16 мм",
    "unit": "м",
    "matches_existing": False,
    "notes": [],
}
REPLY = {
    "status": "ready",
    "message": "Собрал позиции",
    "questions": [],
    "lines": [{"title": "Кабель UTP Cat6", "quantity": 305, "unit": "м", "purpose": "камеры"}],
    "warnings": [],
    "recommendations": [],
}


def rows(session) -> list[AiInteraction]:
    return list(session.scalars(select(AiInteraction).order_by(AiInteraction.id)))


# --- Что попадает в журнал ----------------------------------------------------


def test_material_advice_is_recorded(client, login, employee, session, assistant_box) -> None:
    assistant_box.answer = ADVICE
    login(employee)

    body = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    assert body["suggested"] == "Гофра гибкая 16 мм"

    (entry,) = rows(session)
    assert entry.kind is AiKind.MATERIAL
    assert entry.question == "гофра16"
    assert entry.answer == "Гофра гибкая 16 мм"
    assert entry.ok is True
    # False, а не None: кнопка «Применить» у совета есть, её пока не
    # нажали. None означало бы, что применять было нечего, и такой ответ
    # не должен попадать в знаменатель доли применённых.
    assert entry.applied is False
    # Имя берётся из сессии, а не из тела запроса.
    assert entry.username == employee.full_name
    assert entry.employee_id == employee.id
    # Номер записи возвращается панели: по нему отмечается «Применить».
    assert body["interaction_id"] == entry.id


def test_request_assistant_is_recorded(client, login, employee, session, assistant_box) -> None:
    assistant_box.answer = REPLY
    login(employee)

    body = client.post(
        "/api/assistant/request",
        json={"text": "нужен кабель на камеры", "context": {"project_name": "Регар"}},
    ).json()

    (entry,) = rows(session)
    assert entry.kind is AiKind.REQUEST
    assert entry.question == "нужен кабель на камеры"
    assert "Кабель UTP Cat6 — 305 м" in entry.answer
    assert body["interaction_id"] == entry.id


def test_analytics_question_is_recorded(client, login, manager, session, assistant_box) -> None:
    """Сводка и вопросы тоже стоят денег — счётчик обращений не должен врать."""
    assistant_box.answer = {"answer": "Всё спокойно", "bullets": [], "requests": [], "recommendations": []}
    login(manager)

    client.post("/api/analytics/ask", json={"question": "что происходит"})

    (entry,) = rows(session)
    assert entry.kind is AiKind.ANALYTICS
    # В журнале видно и вопрос, и выбранное намерение: по нему потом
    # понятно, какую именно функцию выполнял сервер.
    assert entry.question == "[overview] что происходит"
    assert entry.answer == "Всё спокойно"


def test_failure_is_recorded_with_reason(client, login, employee, session, assistant_box) -> None:
    """Модель не ответила — это тоже обращение, и причина нужна для разбора."""
    assistant_box.answer = None  # Box без ответа бросает AssistantError
    login(employee)

    body = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    assert body["available"] is False

    (entry,) = rows(session)
    assert entry.ok is False
    assert entry.error == "модель не отвечает"
    assert entry.answer is None


def test_cached_answer_is_recorded_without_timing(
    client, login, employee, session, assistant_box
) -> None:
    """Ответ из кэша человек тоже увидел, но модель мы не ждали."""
    assistant_box.answer = ADVICE
    login(employee)

    client.post("/api/materials/advice", json={"title": "гофра16"})
    client.post("/api/materials/advice", json={"title": "гофра16"})

    first, second = rows(session)
    assert len(assistant_box.prompts) == 1, "второй раз к модели не ходим"
    assert first.duration_ms is not None
    assert second.duration_ms is None, "среднее время не должно улучшаться от кэша"
    assert first.id != second.id, "у каждого свой номер, чужой не переиспользуем"


def test_secrets_never_reach_the_journal(client, login, employee, session, assistant_box) -> None:
    """Ключ Anthropic в записи не появляется ни при удаче, ни при отказе."""
    assistant_box.answer = ADVICE
    login(employee)
    client.post("/api/materials/advice", json={"title": "гофра16"})

    for entry in rows(session):
        dump = " ".join(str(v) for v in vars(entry).values())
        assert "test-key" not in dump
        assert "sk-ant" not in dump


def test_long_text_is_cut(session) -> None:
    entry_id = ai_log.record(session, kind=AiKind.REQUEST, question="я" * 5000)
    entry = session.get(AiInteraction, entry_id)
    assert len(entry.question) == ai_log.TEXT_LIMIT
    assert entry.question.endswith("…")


# --- «Применить» ---------------------------------------------------------------


def test_applied_is_marked(client, login, employee, session, assistant_box) -> None:
    assistant_box.answer = ADVICE
    login(employee)
    advice = client.post("/api/materials/advice", json={"title": "гофра16"}).json()

    assert client.post(f"/api/ai/applied/{advice['interaction_id']}").status_code == 204

    session.expire_all()
    (entry,) = rows(session)
    assert entry.applied is True


def test_foreign_interaction_is_not_found(client, login, employee, manager, session) -> None:
    """Чужое обращение не находится — как чужая заявка."""
    from app.core.audit_context import Actor, set_actor

    set_actor(Actor(id=manager.id, name=manager.full_name))
    entry_id = ai_log.record(session, kind=AiKind.REQUEST, question="чужой вопрос")
    set_actor(None)

    login(employee)
    assert client.post(f"/api/ai/applied/{entry_id}").status_code == 404


def test_applied_requires_login(client) -> None:
    assert client.post("/api/ai/applied/1").status_code == 401


# --- Настройки для администратора ---------------------------------------------


@pytest.mark.parametrize("role_fixture", ["employee", "manager", "procurement"])
def test_ai_settings_closed_to_others(client, login, request, role_fixture) -> None:
    login(request.getfixturevalue(role_fixture))
    assert client.get("/api/ai/settings").status_code == 403


def test_ai_settings_shows_masked_key(client, login, admin, assistant_box) -> None:
    """Ключ виден настолько, чтобы отличить его от старого, и не больше."""
    login(admin)
    body = client.get("/api/ai/settings").json()

    assert body["enabled"] is True
    assert body["key_mask"] == "…-key"
    assert "test-key" not in str(body)


def test_ai_settings_counts_usage(client, login, admin, employee, session, assistant_box) -> None:
    assistant_box.answer = ADVICE
    login(employee)
    advice = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    client.post(f"/api/ai/applied/{advice['interaction_id']}")
    assistant_box.answer = None
    client.post("/api/materials/advice", json={"title": "хомут 300"})

    login(admin)
    body = client.get("/api/ai/settings").json()
    assert body["usage"]["total"] == 2
    assert body["usage"]["failed"] == 1
    assert body["usage"]["applied"] == 1
    assert body["usage"]["by_kind"] == {"MATERIAL": 2}
    assert [e["question"] for e in body["recent"]] == ["хомут 300", "гофра16"]


def test_journal_survives_without_ai(client, login, employee, session) -> None:
    """Помощник выключен — обращений нет, и форма работает как раньше."""
    from app.core import assistant

    assistant.set_transport(None)
    login(employee)
    body = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    assert body == {
        "enabled": False,
        "available": False,
        "title": "гофра16",
        "suggested": None,
        "changed": False,
        "unit": None,
        "matches_existing": False,
        "notes": [],
        "interaction_id": None,
    }
    assert rows(session) == []


def test_request_lifecycle_is_untouched(session, employee, project) -> None:
    """Журнал AI ничего не меняет в пути заявки: коммит внутри записи не
    должен утаскивать с собой чужую незавершённую работу."""
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Кабель", quantity=1, unit="м")],
            submit=True,
        ),
    )
    session.commit()
    assert request.status is RequestStatus.PENDING
