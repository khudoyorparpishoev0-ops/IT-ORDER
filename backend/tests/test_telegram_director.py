"""Директорский режим бота: те же расчёты, что в панели, и те же права.

Главное, что проверяется: аналитики для Telegram отдельной нет; обычный
сотрудник её не видит вовсе; модель не получает лишнего и не пишет SQL;
длинные списки идут страницами.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.time import utcnow
from app.db.models import AiInteraction, AiSource, AuditLog, ExpenseRequest
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import requests as svc
from app.services import telegram_director as director
from app.services.analytics import executive, scope

CHAT = 800

# Порядок фикстур важен: assistant_box сбрасывает кэш настроек и создаёт
# новый Settings, а telegram_box правит в нём токен бота.


def hook(client, payload: dict):
    secret = get_settings().telegram_webhook_secret
    return client.post(f"/api/telegram/webhook/{secret}", json=payload)


def says(client, text: str, chat_id: int = CHAT):
    return hook(client, {"message": {"chat": {"id": chat_id}, "text": text}})


def presses(client, code: str, chat_id: int = CHAT):
    return hook(
        client,
        {"callback_query": {"id": "1", "data": code, "message": {"chat": {"id": chat_id}}}},
    )


def linked(session, employee, chat_id: int = CHAT):
    employee.telegram_chat_id = chat_id
    session.commit()
    return employee


def last(box) -> str:
    return box[-1].text


def buttons(box) -> list[str]:
    return [code for _, code in box[-1].choices]


def submit(session, employee, project, *titles, hours_old: int = 0):
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title=t, quantity=1, unit="шт.") for t in titles],
            submit=True,
        ),
    )
    session.commit()
    if hours_old:
        row = session.get(ExpenseRequest, request.id)
        moment = utcnow() - timedelta(hours=hours_old)
        row.created_at = moment
        row.submitted_at = moment
        session.commit()
    return request


# --- Права ---------------------------------------------------------------------


def test_employee_has_no_director_block(client, session, employee, telegram_box) -> None:
    """Сотруднику директорских кнопок не видно — их просто нет."""
    linked(session, employee)
    says(client, "/menu")
    codes = buttons(telegram_box)
    assert not [c for c in codes if c.startswith("dir:")]


def test_employee_command_is_refused(client, session, employee, project, telegram_box) -> None:
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, employee)

    says(client, "/summary")
    assert "доступна руководителю" in last(telegram_box)


def test_employee_button_is_refused(client, session, employee, telegram_box) -> None:
    """Кнопку можно нажать из старого сообщения — право проверяется снова."""
    linked(session, employee)
    presses(client, director.DIR_ATTENTION)
    assert "доступна руководителю" in last(telegram_box)


def test_procurement_has_no_analytics(client, session, procurement, telegram_box) -> None:
    """У закупа есть view_all_requests, но нет view_reports."""
    linked(session, procurement, chat_id=801)
    says(client, "/summary", chat_id=801)
    assert "доступна руководителю" in last(telegram_box)


@pytest.mark.parametrize("role_fixture", ["manager", "finance", "admin"])
def test_reports_right_opens_director_block(
    client, session, request, role_fixture, telegram_box
) -> None:
    person = request.getfixturevalue(role_fixture)
    linked(session, person, chat_id=810)
    says(client, "/menu", chat_id=810)
    assert director.DIR_OVERVIEW in buttons(telegram_box)


def test_disabled_employee_gets_nothing(client, session, manager, telegram_box) -> None:
    linked(session, manager)
    manager.active = False
    session.commit()

    says(client, "/summary")
    assert "отключена" in last(telegram_box)


# --- Границы видимости ------------------------------------------------------------


def test_scope_follows_the_existing_permission(employee, manager, finance, admin) -> None:
    """Обзор берётся из view_all_requests, а не задаётся заново.

    Руководитель и так видит каждую заявку в разделе «Заявки»: сузить
    одну аналитику значило бы изобразить защиту, а не дать её.
    """
    assert scope.for_employee(manager).all_company is True
    assert scope.for_employee(finance).all_company is True
    assert scope.for_employee(admin).all_company is True
    assert scope.can_see_analytics(employee) is False


def test_narrow_scope_hides_foreign_requests(session, employee, manager, project) -> None:
    """Если обзор сузили, чужие заявки в аналитику не попадают."""
    submit(session, manager, project, "Чужая заявка", hours_old=30)
    narrow = scope.Scope(employee_id=employee.id, all_company=False)

    data = executive.overview(session, scope=narrow)
    assert data.active_requests == 0
    assert data.requires_attention == 0

    wide = scope.Scope(employee_id=manager.id, all_company=True)
    assert executive.overview(session, scope=wide).active_requests == 1


# --- Те же расчёты, что в панели ----------------------------------------------------


def test_bot_summary_matches_the_panel(
    client, session, manager, employee, project, telegram_box
) -> None:
    """Отдельной аналитики для бота нет: цифры те же."""
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "/summary")
    text = last(telegram_box)

    data = executive.overview(session, scope=scope.for_employee(manager))
    assert f"Активные: {data.active_requests}" in text
    assert f"Просрочено: {data.overdue}" in text
    assert f"Требуют внимания: {data.requires_attention}" in text
    assert "ORDER Intelligence" in text


def test_summary_has_no_long_list(
    client, session, manager, employee, project, telegram_box
) -> None:
    """Десятки заявок одним сообщением не отправляем."""
    for i in range(12):
        submit(session, employee, project, f"Материал {i}", hours_old=30)
    linked(session, manager)

    says(client, "/summary")
    text = last(telegram_box)
    assert len(text) < director.MAX_TEXT
    assert text.count("РЗ-") <= 1


def test_word_summary_works(client, session, manager, employee, project, telegram_box) -> None:
    """Слово «Сводка» — то же, что /summary: команды с телефона не набирают."""
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "Сводка")
    assert "ORDER Intelligence" in last(telegram_box)


# --- Страницы ------------------------------------------------------------------------


def test_attention_is_paginated(
    client, session, manager, employee, project, telegram_box
) -> None:
    for i in range(12):
        submit(session, employee, project, f"Материал {i}", hours_old=30)
    linked(session, manager)

    says(client, "/attention")
    first = last(telegram_box)
    assert first.count("РЗ-") == director.PAGE_SIZE
    codes = buttons(telegram_box)
    assert any(c.startswith("dir:page:att:1") for c in codes)
    assert not any("dir:page:att:-" in c for c in codes), "назад с первой некуда"

    presses(client, "dir:page:att:1")
    second = last(telegram_box)
    assert second != first
    assert any(c.startswith("dir:page:att:0") for c in buttons(telegram_box))


def test_short_list_has_no_pagination(
    client, session, manager, employee, project, telegram_box
) -> None:
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "/attention")
    assert buttons(telegram_box) == []


def test_page_out_of_range_is_clamped(
    client, session, manager, employee, project, telegram_box
) -> None:
    """Кнопка из старого сообщения может указывать в никуда."""
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    presses(client, "dir:page:att:99")
    assert "РЗ-" in last(telegram_box)


def test_empty_queue_says_so(client, session, manager, telegram_box) -> None:
    linked(session, manager)
    says(client, "/attention")
    assert "всё в срок" in last(telegram_box).lower()


# --- Просрочки и застой ----------------------------------------------------------------


def test_overdue_and_stuck_are_different_lists(
    client, session, manager, employee, project, telegram_box
) -> None:
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "/overdue")
    assert "Просроченные" in last(telegram_box)

    says(client, "/stuck")
    # Норматив нарушен, значит в «без движения» её быть не должно.
    assert "застоя нет" in last(telegram_box)


def test_projects_list(client, session, manager, employee, project, telegram_box) -> None:
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "/projects")
    assert project.name in last(telegram_box)


# --- Ссылки на заявки --------------------------------------------------------------------


def test_deep_link_points_at_the_request(
    client, session, manager, employee, project, telegram_box
) -> None:
    """Ссылка ведёт к карточке заявки и ничего секретного не несёт."""
    request = submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "/attention")
    message = telegram_box[-1]
    text = message.text
    assert f"/requests/{request.id}" in text
    # Кнопка ведёт в раздел, номер заявки — в саму заявку.
    assert message.button and message.button[1].endswith("/intelligence")
    for secret in ("token", "secret", "session", "?key"):
        assert secret not in text.lower()


# --- Сводки за период ----------------------------------------------------------------------


@pytest.mark.parametrize("command, marker", [("/morning", "Активные"), ("/evening", "Осталось активных")])
def test_digests_work_on_demand(
    client, session, manager, employee, project, telegram_box, command, marker
) -> None:
    """По запросу, а не по расписанию: рассылка — отдельная работа."""
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, command)
    assert marker in last(telegram_box)


def test_digests_are_closed_to_employees(client, session, employee, telegram_box) -> None:
    linked(session, employee)
    says(client, "/morning")
    assert "доступна руководителю" in last(telegram_box)


def test_no_scheduled_digest_job() -> None:
    """Автоматическая рассылка сводок в этой фазе не включается."""
    from app.services.jobs import HANDLERS

    assert not [name for name in HANDLERS if "digest" in name]


# --- Вопрос руководителя ---------------------------------------------------------------------


def test_ask_uses_the_intent_registry(
    client, session, manager, employee, project, assistant_box, telegram_box
) -> None:
    request = submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    assistant_box.by_schema = {"_Intent": {"intent": "overdue"}}
    assistant_box.answer = {
        "answer": "Одна заявка вышла за норматив.",
        "bullets": [],
        "requests": [{"number": request.number, "why": "стоит 30 часов"}],
        "recommendations": [],
    }

    says(client, "/ask какие заявки зависли")
    text = last(telegram_box)
    assert "вышла за норматив" in text
    assert f"/requests/{request.id}" in text

    # Первый запрос — выбор намерения, данных в нём нет.
    assert "overdue" in assistant_box.prompts[0]
    assert request.number not in assistant_box.prompts[0]
    # Второй — ответ по данным, которые достал сервер.
    assert "ДАННЫЕ (overdue)" in assistant_box.prompts[1]


def test_model_never_sees_sql_or_the_database(
    client, session, manager, employee, project, assistant_box, telegram_box
) -> None:
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)
    assistant_box.by_schema = {"_Intent": {"intent": "overview"}}
    assistant_box.answer = {"answer": "ок", "bullets": [], "requests": [], "recommendations": []}

    says(client, "/ask что происходит")

    for prompt in assistant_box.prompts:
        low = prompt.lower()
        for forbidden in ("select ", "insert ", "update ", "delete ", "postgres", "password"):
            assert forbidden not in low


def test_ask_falls_back_when_the_model_fails(
    client, session, manager, employee, project, assistant_box, telegram_box
) -> None:
    """Классификация не удалась — не тупик: предлагаем то, что считает база."""
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)
    assistant_box.answer = None  # модель не отвечает вовсе

    says(client, "/ask что-то непонятное")
    assert "Не удалось точно определить запрос" in last(telegram_box)
    codes = buttons(telegram_box)
    assert director.DIR_OVERVIEW in codes
    assert director.DIR_OVERDUE in codes


def test_ask_without_a_key_offers_numbers(client, session, manager, telegram_box) -> None:
    from app.core import assistant

    assistant.set_transport(None)
    linked(session, manager)

    says(client, "/ask что происходит")
    assert "цифры на месте" in last(telegram_box)


def test_ask_without_a_question_shows_examples(client, session, manager, telegram_box) -> None:
    linked(session, manager)
    says(client, "/ask")
    assert "требует моего внимания" in last(telegram_box)


def test_ask_is_closed_to_employees(client, session, employee, telegram_box) -> None:
    linked(session, employee)
    says(client, "/ask что происходит")
    assert "доступна руководителю" in last(telegram_box)


# --- Оценка ответа ------------------------------------------------------------------------------


def test_feedback_only_under_ai_answers(
    client, session, manager, employee, project, assistant_box, telegram_box
) -> None:
    """Под обычной сводкой оценивать нечего: там цифры базы, а не мнение."""
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "/summary")
    assert not [c for c in buttons(telegram_box) if c.startswith(director.DIR_RATE)]

    assistant_box.by_schema = {"_Intent": {"intent": "overview"}}
    assistant_box.answer = {"answer": "ок", "bullets": [], "requests": [], "recommendations": []}
    says(client, "/ask что происходит")
    assert [c for c in buttons(telegram_box) if c.startswith(director.DIR_RATE)]


def test_feedback_is_saved(
    client, session, manager, employee, project, assistant_box, telegram_box
) -> None:
    from app.db.models import AiFeedback

    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)
    assistant_box.by_schema = {"_Intent": {"intent": "overview"}}
    assistant_box.answer = {"answer": "ок", "bullets": [], "requests": [], "recommendations": []}

    says(client, "/ask что происходит")
    code = next(c for c in buttons(telegram_box) if c.startswith(director.DIR_RATE))
    presses(client, code)

    (row,) = session.scalars(select(AiFeedback)).all()
    assert row.useful is True
    assert row.employee_id == manager.id


# --- Журнал -----------------------------------------------------------------------------------------


def test_director_requests_are_logged(
    client, session, manager, employee, project, telegram_box
) -> None:
    """Данные всей компании — доступ должен оставлять след."""
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)

    says(client, "/summary")

    rows = session.scalars(select(AuditLog).where(AuditLog.entity == "analytics")).all()
    assert [r.action for r in rows] == ["analytics_view"]
    assert rows[0].username == manager.full_name
    assert "telegram" in rows[0].details
    assert "без AI" in rows[0].details


def test_ai_question_is_logged_with_intent_and_latency(
    client, session, manager, employee, project, assistant_box, telegram_box
) -> None:
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)
    assistant_box.by_schema = {"_Intent": {"intent": "overdue"}}
    assistant_box.answer = {"answer": "ок", "bullets": [], "requests": [], "recommendations": []}

    says(client, "/ask что зависло")

    rows = session.scalars(select(AuditLog).where(AuditLog.entity == "analytics")).all()
    (row,) = rows
    assert row.action == "ai_question"
    assert row.entity_id == "overdue"
    assert "telegram" in row.details
    assert "с AI" in row.details
    assert "мс" in row.details
    # Промпта и ответа модели в журнале нет: он про «кто смотрел».
    assert "ДАННЫЕ" not in (row.details or "")


def test_source_is_telegram(
    client, session, manager, employee, project, assistant_box, telegram_box
) -> None:
    submit(session, employee, project, "Цемент М500", hours_old=30)
    linked(session, manager)
    assistant_box.by_schema = {"_Intent": {"intent": "overview"}}
    assistant_box.answer = {"answer": "ок", "bullets": [], "requests": [], "recommendations": []}

    says(client, "/ask что происходит")

    entries = session.scalars(select(AiInteraction)).all()
    assert entries and all(e.source is AiSource.TELEGRAM for e in entries)
