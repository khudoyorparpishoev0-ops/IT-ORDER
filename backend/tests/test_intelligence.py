"""AI-аналитик: права, готовые цифры, поведение при сбое модели."""

from __future__ import annotations

import pytest

from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import intelligence
from app.services import requests as svc


def need(session, employee, project, title="Кабель UTP Cat6"):
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title=title, quantity=1, unit="м")],
            submit=True,
        ),
    )
    session.flush()
    return request


# --- Права -------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/analytics/digest"])
def test_employee_has_no_analytics(client, login, employee, path) -> None:
    """Сотруднику аналитика по компании закрыта."""
    login(employee)
    assert client.get(path).status_code == 403
    assert client.post("/api/analytics/ask", json={"question": "что происходит"}).status_code == 403


def test_procurement_has_no_analytics(client, login, procurement) -> None:
    """Закупу тоже: сводка по всей компании — не его дело."""
    login(procurement)
    assert client.get("/api/analytics/digest").status_code == 403


@pytest.mark.parametrize("role_fixture", ["manager", "finance", "admin"])
def test_analytics_open_to_manager_finance_admin(
    client, login, request, role_fixture
) -> None:
    login(request.getfixturevalue(role_fixture))
    assert client.get("/api/analytics/digest").status_code == 200


def test_anonymous_is_rejected(client) -> None:
    assert client.get("/api/analytics/digest").status_code == 401


# --- Сводка ------------------------------------------------------------------


def test_digest_returns_numbers_without_ai(client, login, manager, employee, project, session) -> None:
    """Без ключа модели сводка приходит с цифрами и без текста."""
    from app.core import assistant

    need(session, employee, project)
    session.commit()
    assistant.set_transport(None)

    login(manager)
    body = client.get("/api/analytics/digest").json()
    assert body["ai"]["enabled"] is False
    assert body["totals"]["active"] == 1
    assert body["blind_spots"]


def test_digest_adds_model_words(client, login, manager, employee, project, session, assistant_box) -> None:
    need(session, employee, project)
    session.commit()
    assistant_box.answer = {
        "headline": "На вас одно решение",
        "summary": ["Заявка РЗ-0001 ждёт согласования покупки"],
        "recommendations": ["Согласовать до конца дня"],
    }

    login(manager)
    body = client.get("/api/analytics/digest").json()
    assert body["ai"] == {
        "enabled": True,
        "available": True,
        "headline": "На вас одно решение",
        "summary": ["Заявка РЗ-0001 ждёт согласования покупки"],
        "recommendations": ["Согласовать до конца дня"],
    }
    # Цифры модель не считает — они уже в запросе к ней.
    assert "СЧЁТЧИКИ" in assistant_box.prompts[-1]
    assert "В работе: 1" in assistant_box.prompts[-1]


def test_model_failure_keeps_the_numbers(client, login, manager, employee, project, session, assistant_box) -> None:
    """Модель молчит — сводка всё равно приходит, но без текста."""
    need(session, employee, project)
    session.commit()

    login(manager)
    body = client.get("/api/analytics/digest").json()
    assert body["ai"] == {"enabled": True, "available": False, "headline": None, "summary": [], "recommendations": []}
    assert body["totals"]["active"] == 1


# --- Вопрос руководителя ------------------------------------------------------


def test_ask_answers_by_prepared_facts(client, login, manager, employee, project, session, assistant_box) -> None:
    request = need(session, employee, project)
    session.commit()
    assistant_box.answer = {
        "answer": "Сейчас требует внимания одна заявка.",
        "bullets": ["Стоит у руководителя дольше норматива"],
        "requests": [{"number": request.number, "why": "ждёт согласования"}],
        "recommendations": [],
    }

    login(manager)
    body = client.post("/api/analytics/ask", json={"question": "Что требует моего внимания?"}).json()
    assert body["available"] is True
    assert body["requests"] == [
        {"id": request.id, "number": request.number, "why": "ждёт согласования"}
    ]
    assert "Вопрос руководителя: Что требует моего внимания?" in assistant_box.prompts[-1]


def test_invented_request_number_is_dropped(client, login, manager, employee, project, session, assistant_box) -> None:
    """Номер, которого нет в фактах, модель придумала: ссылку не делаем."""
    need(session, employee, project)
    session.commit()
    assistant_box.answer = {
        "answer": "Проверьте заявку.",
        "bullets": [],
        "requests": [{"number": "РЗ-9999", "why": "выдумка"}],
        "recommendations": [],
    }

    login(manager)
    body = client.post("/api/analytics/ask", json={"question": "какие заявки зависли"}).json()
    assert body["requests"] == []


def test_question_goes_to_the_audit_log(client, login, manager, employee, project, session, assistant_box) -> None:
    """Аналитика показывает данные всей компании — след обращения нужен."""
    need(session, employee, project)
    session.commit()
    assistant_box.answer = {"answer": "ок", "bullets": [], "requests": [], "recommendations": []}

    login(manager)
    client.post("/api/analytics/ask", json={"question": "сколько заявок Регара"})

    from app.db.models import AuditLog
    from sqlalchemy import select

    rows = session.scalars(select(AuditLog).where(AuditLog.entity == "analytics")).all()
    assert [r.action for r in rows] == ["ai_question"]
    assert rows[0].details == "сколько заявок Регара"
    assert rows[0].username == manager.full_name


def test_ask_without_key_says_so(client, login, manager) -> None:
    from app.core import assistant

    assistant.set_transport(None)
    login(manager)
    body = client.post("/api/analytics/ask", json={"question": "что происходит"}).json()
    assert body == {
        "enabled": False,
        "available": False,
        "answer": "",
        "bullets": [],
        "requests": [],
        "recommendations": [],
    }


def test_history_reaches_the_model(client, login, manager, employee, project, session, assistant_box) -> None:
    need(session, employee, project)
    session.commit()
    assistant_box.answer = {"answer": "ок", "bullets": [], "requests": [], "recommendations": []}

    login(manager)
    client.post(
        "/api/analytics/ask",
        json={
            "question": "а по объектам?",
            "history": [
                {"role": "user", "text": "что требует внимания"},
                {"role": "assistant", "text": "одна заявка"},
            ],
        },
    )
    assert assistant_box.histories[-1] == [
        ("user", "что требует внимания"),
        ("assistant", "одна заявка"),
    ]
