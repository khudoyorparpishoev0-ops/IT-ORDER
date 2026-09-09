"""Фаза 4: срок хранения журнала, приватность подсказок, оценки,
ранжирование памяти, нечёткий поиск и «как в прошлый раз»."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.time import utcnow
from app.db.models import (
    AiFeedback,
    AiInteraction,
    AiKind,
    AuditLog,
    ExpenseLine,
    ExpenseRequest,
    Project,
)
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import ai_feedback, ai_log, ai_memory, ai_privacy
from app.services import requests as svc

ADVICE = {
    "normalized": "Гофра гибкая 16 мм",
    "unit": "м",
    "matches_existing": False,
    "notes": [],
}


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


def aged(session, entry_id: int, days: int) -> None:
    """Состаривает запись журнала: в тестах ждать 180 дней нечем."""
    entry = session.get(AiInteraction, entry_id)
    entry.created_at = utcnow() - timedelta(days=days)
    session.commit()


# --- Срок хранения журнала -------------------------------------------------------


def test_old_records_are_purged(session, employee, project) -> None:
    from app.core.audit_context import Actor, set_actor

    set_actor(Actor(id=employee.id, name=employee.full_name))
    old = ai_log.record(session, kind=AiKind.MATERIAL, question="давнее")
    fresh = ai_log.record(session, kind=AiKind.MATERIAL, question="свежее")
    set_actor(None)
    aged(session, old, days=200)

    details = ai_log.purge_old(session)
    assert "удалено 1" in details
    assert [e.question for e in session.scalars(select(AiInteraction))] == ["свежее"]
    assert session.get(AiInteraction, fresh) is not None


def test_retention_period_is_configurable(session, monkeypatch) -> None:
    from app.config import get_settings

    entry = ai_log.record(session, kind=AiKind.MATERIAL, question="месяц назад")
    aged(session, entry, days=40)

    monkeypatch.setattr(get_settings(), "ai_interactions_retention_days", 30)
    ai_log.purge_old(session)
    assert session.scalars(select(AiInteraction)).all() == []


def test_purge_never_touches_the_request(session, employee, project) -> None:
    """Журнал AI вспомогательный: заявки, их текст и история — не его дело."""
    request = submit(session, employee, project, "ГОФРА 16 ММ.")
    entry = ai_log.record(session, kind=AiKind.REQUEST, question="что нужно")
    aged(session, entry, days=200)

    ai_log.purge_old(session)
    session.expire_all()

    kept = session.get(ExpenseRequest, request.id)
    assert kept is not None
    assert kept.number == request.number
    # Оригинальное написание и приведённое остались на месте.
    assert [(l.title, l.normalized_text) for l in kept.lines] == [
        ("ГОФРА 16 ММ.", "гофра 16 мм")
    ]
    assert kept.status is request.status
    # Журнал действий по заявке — тоже.
    assert session.scalars(select(AuditLog).where(AuditLog.entity == "request")).all()


def test_purge_takes_the_feedback_with_it(session, employee) -> None:
    """Оценка несуществующего ответа не значит ничего."""
    from app.core.audit_context import Actor, set_actor

    set_actor(Actor(id=employee.id, name=employee.full_name))
    entry = ai_log.record(session, kind=AiKind.MATERIAL, question="давнее")
    set_actor(None)
    ai_feedback.rate(session, employee, interaction_id=entry, useful=False, reason="stale")
    aged(session, entry, days=200)

    ai_log.purge_old(session)
    assert session.scalars(select(AiFeedback)).all() == []


def test_purge_job_is_scheduled() -> None:
    from app.services.jobs import HANDLERS, JOB_LABEL
    from app.services.schedule import AI_RETENTION

    assert HANDLERS[AI_RETENTION] is ai_log.purge_old
    assert AI_RETENTION in JOB_LABEL


# --- Приватность корпоративных подсказок -------------------------------------------


def test_material_is_shared_person_is_not(client, login, employee, manager, project, session) -> None:
    """«UTP Cat6 — часто на объекте Регар» можно; «Начиб заказывал его за
    3 355 сомони» — нет."""
    submit(session, manager, project, "UTP Cat6 Outdoor")

    login(employee)
    body = client.get(f"/api/assistant/memory?project_id={project.id}").json()

    names = [x["title"] for x in body["frequent"]]
    assert names == ["UTP Cat6 Outdoor"]
    # Ни имени, ни суммы, ни комментария в подсказке нет ни у кого.
    for block in ("frequent", "mine", "recent", "project"):
        for item in body[block]:
            assert set(item) == {"title", "unit", "times", "last_number", "last_date"}
            assert manager.full_name not in str(item)


def test_own_history_is_only_own(client, login, employee, manager, project, session) -> None:
    submit(session, manager, project, "Личный материал руководителя")

    login(employee)
    body = client.get("/api/assistant/memory").json()
    assert body["mine"] == []
    assert body["recent"] == []


def test_strip_person_removes_names_and_money(session, employee, manager) -> None:
    item = {"title": "Кабель", "employee": manager.full_name, "amount": "3355.00"}
    assert ai_privacy.strip_person(item, employee) == {"title": "Кабель"}
    # У кого право видеть чужие заявки — видит всё как есть.
    assert ai_privacy.strip_person(item, manager) == item


def test_visible_scope_follows_the_right(session, employee, manager) -> None:
    assert ai_privacy.visible_employee_id(employee) == employee.id
    assert ai_privacy.visible_employee_id(manager) is None


# --- Ранжирование памяти -----------------------------------------------------------


def test_ranking_prefers_own_project(session, employee, manager, project) -> None:
    other = Project(name="Регар")
    session.add(other)
    session.flush()

    mine_here = submit(session, employee, project, "Кабель UTP Cat6")
    submit(session, employee, other, "Кабель UTP Cat6")
    submit(session, manager, project, "Кабель UTP Cat6")

    top = ai_memory.ranked(
        session, employee_id=employee.id, project_id=project.id, materials=["Кабель UTP Cat6"]
    )
    assert top[0].number == mine_here.number
    assert "ваша заявка на этом объекте" in top[0].reasons


def test_same_material_lifts_the_score(session, employee, project) -> None:
    plain = submit(session, employee, project, "Бетон М300")
    with_material = submit(session, employee, project, "Гофра 16 мм")

    top = ai_memory.ranked(
        session, employee_id=employee.id, project_id=project.id, materials=["гофра16"]
    )
    assert top[0].number == with_material.number
    assert top[0].score > next(t for t in top if t.number == plain.number).score


def test_fresh_beats_old(session, employee, project) -> None:
    old = submit(session, employee, project, "Цемент М500")
    fresh = submit(session, employee, project, "Цемент М500")
    old_row = session.get(ExpenseRequest, old.id)
    old_row.created_at = utcnow() - timedelta(days=120)
    session.commit()

    top = ai_memory.ranked(session, employee_id=employee.id, project_id=project.id)
    assert top[0].number == fresh.number


def test_ranking_respects_visibility(session, employee, manager, project) -> None:
    submit(session, manager, project, "Чужая заявка")
    assert (
        ai_memory.ranked(
            session, employee_id=employee.id, visible_employee_id=employee.id
        )
        == []
    )
    assert ai_memory.ranked(session, employee_id=manager.id, visible_employee_id=None)


def test_context_is_bounded(session, employee, project) -> None:
    """Из пятисот заявок модели уходят единицы: токены, задержка и риск."""
    for i in range(15):
        submit(session, employee, project, f"Материал {i}")
    assert len(ai_memory.ranked(session, employee_id=employee.id)) == ai_memory.CONTEXT_LIMIT


# --- Нечёткий поиск ------------------------------------------------------------------


@pytest.mark.parametrize("query", ["гофра16", "ГОФРА 16", "гофра  16  мм"])
def test_fuzzy_search_finds_the_material(session, employee, project, query) -> None:
    submit(session, employee, project, "Гофра 16 мм")
    assert [x.title for x in ai_memory.search_materials(session, text=query)] == [
        "Гофра 16 мм"
    ]


def test_search_follows_a_known_alias(session, employee, project) -> None:
    from app.db.models import MaterialAlias

    submit(session, employee, project, "Гофра гибкая 16 мм")
    session.add(
        MaterialAlias(alias="гофра 16", canonical="Гофра гибкая 16 мм", unit="м", uses=1)
    )
    session.commit()

    assert [x.title for x in ai_memory.search_materials(session, text="гофра16")] == [
        "Гофра гибкая 16 мм"
    ]


def test_search_of_nothing_finds_nothing(session) -> None:
    assert ai_memory.search_materials(session, text="   ") == []


# --- «Как в прошлый раз» ---------------------------------------------------------------


def test_repeat_offers_but_never_creates(client, login, employee, project, session) -> None:
    request = submit(session, employee, project, "Кабель UTP Cat6")

    login(employee)
    body = client.post(
        "/api/assistant/repeat", json={"text": "мне опять этот кабель"}
    ).json()

    assert [o["number"] for o in body["options"]] == [request.number]
    assert body["options"][0]["lines"][0]["title"] == "Кабель UTP Cat6"
    # Заявка не создана: показали вариант, решает человек.
    assert len(session.scalars(select(ExpenseRequest)).all()) == 1


def test_repeat_narrows_by_project(client, login, employee, project, session) -> None:
    other = Project(name="Регар")
    session.add(other)
    session.flush()
    submit(session, employee, project, "Цемент М500")
    at_regar = submit(session, employee, other, "Цемент М500")

    login(employee)
    body = client.post(
        "/api/assistant/repeat",
        json={"text": "как вчера, но на Регар", "project_id": other.id},
    ).json()
    assert body["options"][0]["number"] == at_regar.number


def test_repeat_sees_only_own(client, login, employee, manager, project, session) -> None:
    submit(session, manager, project, "Чужой кабель")

    login(employee)
    assert client.post("/api/assistant/repeat", json={"text": "повтори"}).json()["options"] == []


def test_repeat_without_history_is_empty(client, login, employee) -> None:
    login(employee)
    assert client.post("/api/assistant/repeat", json={"text": "как в прошлый раз"}).json() == {
        "options": []
    }


def test_repeat_requires_login(client) -> None:
    assert client.post("/api/assistant/repeat", json={"text": "повтори"}).status_code == 401


# --- Оценки ------------------------------------------------------------------------------


def test_feedback_is_saved(client, login, employee, session, assistant_box) -> None:
    assistant_box.answer = ADVICE
    login(employee)
    advice = client.post("/api/materials/advice", json={"title": "гофра16"}).json()

    assert (
        client.post(
            "/api/ai/feedback",
            json={
                "interaction_id": advice["interaction_id"],
                "useful": False,
                "reason": "wrong_material",
                "comment": "совсем не то",
            },
        ).status_code
        == 204
    )

    (row,) = session.scalars(select(AiFeedback)).all()
    assert row.useful is False
    assert row.reason == "wrong_material"
    assert row.comment == "совсем не то"
    assert row.employee_id == employee.id


def test_second_opinion_replaces_the_first(client, login, employee, session, assistant_box) -> None:
    assistant_box.answer = ADVICE
    login(employee)
    advice = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    body = {"interaction_id": advice["interaction_id"], "useful": False, "reason": "stale"}

    client.post("/api/ai/feedback", json=body)
    client.post("/api/ai/feedback", json={**body, "useful": True})

    rows = session.scalars(select(AiFeedback)).all()
    assert len(rows) == 1
    assert rows[0].useful is True
    # У «полезно» причины нет: лишний экран ради данных, которыми не пользуются.
    assert rows[0].reason is None


def test_foreign_interaction_cannot_be_rated(client, login, employee, manager, session) -> None:
    from app.core.audit_context import Actor, set_actor

    set_actor(Actor(id=manager.id, name=manager.full_name))
    entry = ai_log.record(session, kind=AiKind.REQUEST, question="чужой вопрос")
    set_actor(None)

    login(employee)
    assert (
        client.post(
            "/api/ai/feedback", json={"interaction_id": entry, "useful": True}
        ).status_code
        == 404
    )


def test_unknown_reason_is_refused(client, login, employee, session, assistant_box) -> None:
    assistant_box.answer = ADVICE
    login(employee)
    advice = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    assert (
        client.post(
            "/api/ai/feedback",
            json={
                "interaction_id": advice["interaction_id"],
                "useful": False,
                "reason": "потому что",
            },
        ).status_code
        == 422
    )


def test_reasons_are_a_closed_list(client, login, employee) -> None:
    login(employee)
    reasons = client.get("/api/ai/feedback/reasons").json()
    assert reasons["wrong_material"] == "Неправильный материал"
    assert "other" in reasons


# --- Метрики качества -------------------------------------------------------------------


def test_quality_metrics_are_counted_by_the_server(
    client, login, admin, employee, session, assistant_box
) -> None:
    assistant_box.answer = ADVICE
    login(employee)
    advice = client.post("/api/materials/advice", json={"title": "гофра16"}).json()
    client.post(f"/api/ai/applied/{advice['interaction_id']}")
    client.post(
        "/api/ai/feedback",
        json={"interaction_id": advice["interaction_id"], "useful": False, "reason": "bad_fix"},
    )
    assistant_box.answer = None
    client.post("/api/materials/advice", json={"title": "хомут 300"})

    login(admin)
    usage = client.get("/api/ai/settings").json()["usage"]
    assert usage["total"] == 2
    assert usage["failed"] == 1
    assert usage["error_pct"] == 50
    assert usage["applied"] == 1
    assert usage["apply_rate_pct"] == 100
    assert usage["total_week"] == 2
    assert usage["useless"] == 1
    assert usage["useless_pct"] == 100
    assert usage["top_reasons"] == [
        {"reason": "bad_fix", "label": "Неправильно исправил текст", "count": 1}
    ]


def test_tokens_are_recorded_when_returned(session, employee) -> None:
    from app.core import assistant

    usage = assistant.Usage(model="claude-opus-5", input_tokens=1200, output_tokens=90)
    entry_id = ai_log.record(
        session, kind=AiKind.REQUEST, question="сколько токенов", usage=usage
    )
    entry = session.get(AiInteraction, entry_id)
    assert (entry.model, entry.input_tokens, entry.output_tokens) == (
        "claude-opus-5",
        1200,
        90,
    )


def test_tokens_are_optional(session) -> None:
    """SDK может не вернуть статистику — метрики это переживают."""
    entry_id = ai_log.record(session, kind=AiKind.REQUEST, question="без статистики")
    entry = session.get(AiInteraction, entry_id)
    assert (entry.model, entry.input_tokens, entry.output_tokens) == (None, None, None)
