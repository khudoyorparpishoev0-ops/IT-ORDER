"""Уведомления в Telegram: привязка чата и сообщения о судьбе заявки."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import get_settings
from app.core import telegram as tg
from app.db.models import Employee, ExpenseRequest, RequestStatus
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import requests as svc
from app.services.telegram_notify import notify_request_state


def _webhook(client, payload: dict):
    secret = get_settings().telegram_webhook_secret
    return client.post(f"/api/telegram/webhook/{secret}", json=payload)


def _start(client, code: str, *, chat_id: int = 500, username: str = "petrov"):
    return _webhook(
        client,
        {
            "message": {
                "chat": {"id": chat_id},
                "from": {"username": username},
                "text": f"/start {code}",
            }
        },
    )


def _make_request(session, employee, project, *, title="Гипсокартон") -> ExpenseRequest:
    return svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title=title, quantity=Decimal("10"), unit="лист")],
        ),
    )


# --- Привязка --------------------------------------------------------------


def test_link_flow(client, session, login, employee, telegram_box):
    """Человек берёт ссылку в панели, открывает её — и чат привязан."""
    login(employee)

    status = client.get("/api/telegram/status").json()
    assert status["configured"] is True
    assert status["linked"] is False

    link = client.post("/api/telegram/link")
    assert link.status_code == 200, link.text
    url = link.json()["url"]
    assert url.startswith("https://t.me/hona_order_bot?start=")
    code = url.rsplit("=", 1)[1]

    assert _start(client, code).status_code == 200
    session.expire_all()
    assert session.get(Employee, employee.id).telegram_chat_id == 500
    assert client.get("/api/telegram/status").json() == {
        "configured": True,
        "linked": True,
        "username": "petrov",
        "bot_username": "hona_order_bot",
    }
    # Бот поздоровался — человек видит, что привязка сработала.
    assert telegram_box and telegram_box[-1].chat_id == 500


def test_link_code_is_single_use(client, session, login, employee, telegram_box):
    login(employee)
    code = client.post("/api/telegram/link").json()["url"].rsplit("=", 1)[1]
    _start(client, code, chat_id=500)

    telegram_box.clear()
    # Тот же код со второго чата не должен подцепить чужого человека.
    _start(client, code, chat_id=777)
    session.expire_all()
    assert session.get(Employee, employee.id).telegram_chat_id == 500
    assert "не подошла" in telegram_box[-1].text


def test_expired_code_rejected(client, session, login, employee, telegram_box):
    from datetime import timedelta

    from app.core.time import utcnow

    login(employee)
    code = client.post("/api/telegram/link").json()["url"].rsplit("=", 1)[1]
    person = session.get(Employee, employee.id)
    person.telegram_link_expires_at = utcnow() - timedelta(minutes=1)
    session.flush()

    _start(client, code)
    session.expire_all()
    assert session.get(Employee, employee.id).telegram_chat_id is None


def test_chat_belongs_to_one_person(
    client, session, login, employee, manager, telegram_box
):
    """Один чат — один сотрудник: иначе кто-то тихо теряет уведомления."""
    login(employee)
    first = client.post("/api/telegram/link").json()["url"].rsplit("=", 1)[1]
    _start(client, first, chat_id=500)

    login(manager)
    second = client.post("/api/telegram/link").json()["url"].rsplit("=", 1)[1]
    telegram_box.clear()
    _start(client, second, chat_id=500)

    session.expire_all()
    assert session.get(Employee, employee.id).telegram_chat_id == 500
    assert session.get(Employee, manager.id).telegram_chat_id is None
    assert "уже привязан" in telegram_box[-1].text


def test_unlink_from_panel_and_from_bot(client, session, login, employee, telegram_box):
    login(employee)
    code = client.post("/api/telegram/link").json()["url"].rsplit("=", 1)[1]
    _start(client, code)

    assert client.post("/api/telegram/unlink").json()["linked"] is False
    session.expire_all()
    assert session.get(Employee, employee.id).telegram_chat_id is None

    # И то же самое командой боту.
    code = client.post("/api/telegram/link").json()["url"].rsplit("=", 1)[1]
    _start(client, code)
    _webhook(client, {"message": {"chat": {"id": 500}, "text": "/stop"}})
    session.expire_all()
    assert session.get(Employee, employee.id).telegram_chat_id is None


def test_webhook_secret_required(client, telegram_box):
    response = client.post("/api/telegram/webhook/не-тот-секрет", json={})
    assert response.status_code == 404


def test_link_requires_configured_bot(client, login, employee):
    """Без токена бота ссылку выдавать нечему — и мы честно об этом говорим."""
    login(employee)
    assert client.get("/api/telegram/status").json()["configured"] is False
    assert client.post("/api/telegram/link").status_code == 422


# --- Уведомления -----------------------------------------------------------


@pytest.fixture
def linked(session):
    """Привязывает чат сотруднику без хождения через бота."""

    def _linked(person: Employee, chat_id: int) -> Employee:
        person.telegram_chat_id = chat_id
        session.flush()
        return person

    return _linked


def test_author_hears_every_step(
    session, employee, manager, procurement, project, advance, linked, telegram_box
):
    linked(employee, 100)

    steps = [
        ("pending", "на согласование"),
        ("sourcing", "передана в отдел закупа"),
        ("priced", "оценена закупом"),
        ("approved", "передана в бухгалтерию"),
    ]
    # На каждый шаг — своя заявка: фикстура `advance` ведёт заявку с начала,
    # а не доводит уже сдвинутую до следующего шага.
    for step, expected in steps:
        request = _make_request(session, employee, project)
        advance(request, to=step)
        session.flush()
        telegram_box.clear()
        notify_request_state(session, request.id)
        mine = [m for m in telegram_box if m.chat_id == 100]
        assert mine, f"автор не получил сообщение на шаге {step}"
        # Первое слово в сообщении с заглавной — сравниваем без регистра.
        assert expected in mine[0].text.lower()
        assert request.number in mine[0].text


def test_next_actor_is_called(
    session, employee, manager, procurement, project, advance, linked, telegram_box
):
    """Заявка легла на чей-то стол — этот человек об этом узнаёт."""
    linked(manager, 200)
    linked(procurement, 300)
    request = _make_request(session, employee, project)

    notify_request_state(session, request.id)
    assert [m.chat_id for m in telegram_box] == [200]
    assert "ждёт вашего решения" in telegram_box[0].text

    telegram_box.clear()
    advance(request, to="sourcing")
    session.flush()
    notify_request_state(session, request.id)
    assert [m.chat_id for m in telegram_box] == [300]
    assert "проверьте склад" in telegram_box[0].text


def test_author_is_not_invited_to_act_on_own_request(
    session, manager, project, linked, telegram_box
):
    """Руководитель подал заявку сам — звать его согласовывать незачем."""
    linked(manager, 200)
    request = _make_request(session, manager, project)

    notify_request_state(session, request.id)
    # Только сообщение автору, приглашения решать нет.
    assert len(telegram_box) == 1
    assert "на согласование" in telegram_box[0].text


def test_rejection_carries_the_reason(
    session, employee, manager, project, linked, telegram_box
):
    from app.schemas.request import DecisionIn

    linked(employee, 100)
    request = _make_request(session, employee, project)
    svc.decide_request(
        session,
        request.id,
        DecisionIn(approve=False, comment="Есть на складе соседнего объекта", actor="Артём Ковалёв"),
    )
    session.flush()

    notify_request_state(session, request.id)
    assert request.status is RequestStatus.REJECTED
    assert "отклонена" in telegram_box[0].text.lower()
    assert "соседнего объекта" in telegram_box[0].text


def test_silence_when_nobody_linked(session, employee, project, telegram_box):
    request = _make_request(session, employee, project)
    notify_request_state(session, request.id)
    assert telegram_box == []


def test_broken_bot_does_not_break_the_request(
    client, session, login, employee, project, telegram_box
):
    """Telegram лежит — заявка всё равно подаётся."""

    class Failing:
        def send(self, message) -> None:
            raise tg.TelegramError("Telegram недоступен")

    employee.telegram_chat_id = 100
    session.flush()
    tg.set_transport(Failing())

    login(employee)
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Гипсокартон", "quantity": "10", "unit": "лист"}],
            "submit": True,
        },
    )
    assert response.status_code == 201, response.text


def test_notification_goes_out_through_the_api(
    client, session, login, employee, manager, project, telegram_box
):
    """Сквозная проверка: подача заявки через API доходит до чата автора."""
    employee.telegram_chat_id = 100
    manager.telegram_chat_id = 200
    session.flush()

    login(employee)
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Гипсокартон", "quantity": "10", "unit": "лист"}],
            "submit": True,
        },
    )
    assert response.status_code == 201, response.text
    chats = {m.chat_id for m in telegram_box}
    assert chats == {100, 200}


# --- Настройка вебхука -----------------------------------------------------


def test_webhook_setup_is_for_admins(client, login, employee, admin, telegram_box, monkeypatch):
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "app.api.routes.telegram.call", lambda method, payload: calls.append((method, payload)) or {"ok": True}
    )

    login(employee)
    assert client.post("/api/telegram/setup").status_code == 403

    login(admin)
    response = client.post("/api/telegram/setup")
    assert response.status_code == 200, response.text
    url = response.json()["webhook_url"]
    assert url.startswith("https://order.it-hona.tj/api/telegram/webhook/")
    assert calls == [("setWebhook", {"url": url, "allowed_updates": ["message"]})]


def test_webhook_setup_needs_a_bot(client, login, admin):
    """Без токена настраивать нечего — говорим это, а не падаем."""
    login(admin)
    response = client.post("/api/telegram/setup")
    assert response.status_code == 422
    assert "TELEGRAM_BOT_TOKEN" in response.json()["detail"]
