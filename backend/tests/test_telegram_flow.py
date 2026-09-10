"""Создание заявки через бота: путь, права и отказы.

Проверяется главное: заявку создаёт тот же сервис, что и панель; без
подтверждения человека ничего не подаётся; права те же, что в панели, и
проверяются на каждом шаге — разговор мог начаться вчера.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    AiSource,
    AiInteraction,
    EmployeeRole,
    ExpenseRequest,
    RequestStatus,
    TelegramSession,
)
from app.services import telegram_flow as flow

CHAT = 700

# Порядок фикстур важен: assistant_box сбрасывает кэш настроек и создаёт
# новый объект Settings, а telegram_box правит в нём токен бота. Возьми
# их в обратном порядке — вебхук ответит 404, потому что бот «не настроен».

REPLY_READY = {
    "status": "ready",
    "message": "Собрал позиции",
    "questions": [],
    "lines": [{"title": "Цемент М500", "quantity": 2, "unit": "мешок", "purpose": "стяжка"}],
    "warnings": [],
    "recommendations": [],
}
REPLY_QUESTION = {
    "status": "need_clarification",
    "message": "Уточню",
    "questions": [{"field": "kind", "question": "Какой цемент?", "options": ["М400", "М500"]}],
    "lines": [],
    "warnings": [],
    "recommendations": [],
}


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


# --- Путь заявки ---------------------------------------------------------------


def test_full_path_creates_the_request(
    client, session, employee, project, assistant_box, telegram_box
) -> None:
    linked(session, employee)
    assistant_box.answer = REPLY_READY

    says(client, "/new")
    assert "На какой объект" in last(telegram_box)
    assert buttons(telegram_box) == [f"p:{project.id}"]

    presses(client, f"p:{project.id}")
    assert "Что нужно" in last(telegram_box)

    says(client, "два мешка цемента")
    card = last(telegram_box)
    assert "Проверьте заявку" in card
    assert "Цемент М500 — 2 мешок" in card
    assert buttons(telegram_box) == ["send", "edit", "cancel"]
    # До подтверждения не создано ничего.
    assert session.scalars(select(ExpenseRequest)).all() == []

    presses(client, "send")
    (request,) = session.scalars(select(ExpenseRequest)).all()
    assert request.status is RequestStatus.PENDING
    assert request.employee_id == employee.id
    assert request.project_id == project.id
    assert [(l.title, l.quantity, l.unit) for l in request.lines] == [
        ("Цемент М500", 2, "мешок")
    ]
    assert request.number in last(telegram_box)
    # Ссылка ведёт к карточке заявки, а не в раздел.
    assert telegram_box[-1].button[1].endswith(f"/requests/{request.id}")
    # Разговор закончен и не мешает следующему.
    assert session.scalars(select(TelegramSession)).all() == []


def test_clarifying_question_offers_buttons(
    client, session, employee, project, assistant_box, telegram_box
) -> None:
    linked(session, employee)
    says(client, "/new")
    presses(client, f"p:{project.id}")

    assistant_box.answer = REPLY_QUESTION
    says(client, "цемент")
    assert "Какой цемент?" in last(telegram_box)
    assert buttons(telegram_box) == ["o:0", "o:1"]

    assistant_box.answer = REPLY_READY
    presses(client, "o:1")
    assert "Проверьте заявку" in last(telegram_box)
    # Нажатый вариант ушёл модели как обычный ответ.
    assert "М500" in assistant_box.prompts[-1]


def test_cancel_creates_nothing(
    client, session, employee, project, assistant_box, telegram_box
) -> None:
    linked(session, employee)
    assistant_box.answer = REPLY_READY
    says(client, "/new")
    presses(client, f"p:{project.id}")
    says(client, "два мешка цемента")

    presses(client, "cancel")
    assert "Отменил" in last(telegram_box)
    assert session.scalars(select(ExpenseRequest)).all() == []
    assert session.scalars(select(TelegramSession)).all() == []


def test_edit_keeps_the_conversation(
    client, session, employee, project, assistant_box, telegram_box
) -> None:
    linked(session, employee)
    assistant_box.answer = REPLY_READY
    says(client, "/new")
    presses(client, f"p:{project.id}")
    says(client, "два мешка цемента")

    presses(client, "edit")
    assert "Что поправить" in last(telegram_box)
    assert session.scalars(select(ExpenseRequest)).all() == []

    says(client, "не два, а три")
    assert "Проверьте заявку" in last(telegram_box)


def test_new_starts_over(client, session, employee, project, assistant_box, telegram_box) -> None:
    """Второй /new затирает прежний разговор: один сотрудник — один."""
    linked(session, employee)
    says(client, "/new")
    presses(client, f"p:{project.id}")
    says(client, "/new")

    (state,) = session.scalars(select(TelegramSession)).all()
    assert state.step == flow.STEP_PROJECT
    assert state.data.get("project_id") is None


# --- Права ---------------------------------------------------------------------


def test_right_is_read_from_the_database(
    client, session, employee, project, telegram_box, monkeypatch
) -> None:
    """Право берётся из базы на каждом сообщении, а не запоминается.

    Роль без права подачи в матрице прав сегодня не заведена, поэтому
    проверяем то, что важно: бот спрашивает матрицу прав, а не помнит
    ответ с прошлого раза.
    """
    from app.core import permissions

    linked(session, employee)
    monkeypatch.setattr(permissions, "has_permission", lambda role, perm: False)
    monkeypatch.setattr(flow, "has_permission", lambda role, perm: False)

    says(client, "/new")
    assert "не каждая роль" in last(telegram_box)
    assert session.scalars(select(TelegramSession)).all() == []


def test_disabled_employee_is_refused(client, session, employee, telegram_box) -> None:
    linked(session, employee)
    employee.active = False
    session.commit()

    says(client, "/new")
    assert "отключена" in last(telegram_box)
    assert session.scalars(select(TelegramSession)).all() == []


def test_role_downgrade_stops_submission(
    client, session, employee, project, assistant_box, telegram_box
) -> None:
    """Разговор начали вчера, а сотрудника отключили: заявка не уйдёт."""
    linked(session, employee)
    assistant_box.answer = REPLY_READY
    says(client, "/new")
    presses(client, f"p:{project.id}")
    says(client, "два мешка цемента")

    employee.active = False
    session.commit()

    presses(client, "send")
    assert session.scalars(select(ExpenseRequest)).all() == []


def test_unlinked_chat_gets_nothing(client, session, telegram_box) -> None:
    says(client, "/new", chat_id=999)
    assert "ни к кому не привязан" in last(telegram_box)


def test_disabled_project_is_refused(
    client, session, employee, project, telegram_box
) -> None:
    linked(session, employee)
    says(client, "/new")
    project.active = False
    session.commit()

    presses(client, f"p:{project.id}")
    assert "отключён" in last(telegram_box)


# --- Помощник недоступен --------------------------------------------------------


def test_without_the_model_the_bot_still_works(
    client, session, employee, project, telegram_box
) -> None:
    """Сбой помощника не закрывает бота: заявку подать можно."""
    linked(session, employee)
    says(client, "/new")
    presses(client, f"p:{project.id}")

    says(client, "Цемент М500 два мешка")
    assert "Помощник сейчас недоступен" in last(telegram_box)
    assert "Цемент М500 два мешка — 1" in last(telegram_box)

    presses(client, "send")
    (request,) = session.scalars(select(ExpenseRequest)).all()
    assert request.lines[0].title == "Цемент М500 два мешка"


def test_stale_button_is_explained(client, session, employee, telegram_box) -> None:
    """Сообщение в Telegram живёт вечно, нажать кнопку могут через час."""
    linked(session, employee)
    presses(client, "send")
    assert "Разговор потерялся" in last(telegram_box)


# --- Журнал ---------------------------------------------------------------------


def test_source_is_telegram(
    client, session, employee, project, assistant_box, telegram_box
) -> None:
    linked(session, employee)
    assistant_box.answer = REPLY_READY
    says(client, "/new")
    presses(client, f"p:{project.id}")
    says(client, "два мешка цемента")

    (entry,) = session.scalars(select(AiInteraction)).all()
    assert entry.source is AiSource.TELEGRAM
    assert entry.employee_id is None or entry.employee_id == employee.id


def test_unknown_text_outside_dialogue_shows_menu(client, session, employee, telegram_box) -> None:
    """Команды с телефона на стройке не набирают — показываем кнопки."""
    linked(session, employee)
    says(client, "привет")
    assert employee.full_name in last(telegram_box)
    assert buttons(telegram_box) == [
        "menu:new",
        "menu:last",
        "menu:frequent",
        "menu:active",
        "menu:ai",
    ]


# --- Быстрые действия и повтор (фаза 4) -----------------------------------------


def test_start_shows_quick_actions(client, session, employee, telegram_box) -> None:
    """После привязки сразу видно, что можно сделать: команды не набирают."""
    from app.config import get_settings
    from app.core.time import utcnow
    from datetime import timedelta

    employee.telegram_link_code = "код-привязки"
    employee.telegram_link_expires_at = utcnow() + timedelta(minutes=30)
    session.commit()

    says(client, "/start код-привязки", chat_id=705)
    assert buttons(telegram_box) == [
        "menu:new",
        "menu:last",
        "menu:frequent",
        "menu:active",
        "menu:ai",
    ]


def test_frequent_button_offers_materials(
    client, session, employee, project, telegram_box
) -> None:
    from app.schemas.request import ExpenseLineIn, RequestCreate
    from app.services import requests as svc

    linked(session, employee)
    svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Цемент М500", quantity=1, unit="мешок")],
            submit=True,
        ),
    )
    session.commit()

    presses(client, "menu:frequent")
    assert "Цемент М500" in last(telegram_box).replace("\n", " ") or any(
        "Цемент М500" in label for label, _ in telegram_box[-1].choices
    )
    assert buttons(telegram_box) == ["m:0"]

    presses(client, "m:0")
    assert "На какой объект" in last(telegram_box)


def test_active_and_last_show_only_own(
    client, session, employee, manager, project, telegram_box
) -> None:
    from app.schemas.request import ExpenseLineIn, RequestCreate
    from app.services import requests as svc

    linked(session, employee)
    svc.create_request(
        session,
        RequestCreate(
            employee_id=manager.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Чужая позиция", quantity=1, unit="шт.")],
            submit=True,
        ),
    )
    session.commit()

    presses(client, "menu:last")
    assert "Заявок пока нет" in last(telegram_box)
    presses(client, "menu:active")
    assert "В работе ничего нет" in last(telegram_box)


def test_repeat_shows_a_card_and_creates_nothing(
    client, session, employee, project, telegram_box
) -> None:
    from app.schemas.request import ExpenseLineIn, RequestCreate
    from app.services import requests as svc

    linked(session, employee)
    svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Кабель UTP Cat6", quantity=2, unit="бухта")],
            submit=True,
        ),
    )
    session.commit()
    before = len(session.scalars(select(ExpenseRequest)).all())

    says(client, "как в прошлый раз")
    assert "Нашёл предыдущий вариант" in last(telegram_box)
    assert "Кабель UTP Cat6" in last(telegram_box)
    assert "r:0" in buttons(telegram_box)
    assert len(session.scalars(select(ExpenseRequest)).all()) == before

    presses(client, "r:0")
    assert "Проверьте заявку" in last(telegram_box)
    assert len(session.scalars(select(ExpenseRequest)).all()) == before

    presses(client, "send")
    assert len(session.scalars(select(ExpenseRequest)).all()) == before + 1


def test_template_is_applied_from_the_bot(
    client, session, employee, project, telegram_box
) -> None:
    from app.services import templates as tsvc

    linked(session, employee)
    tsvc.create(
        session,
        employee,
        name="Заправка Opel",
        lines=[{"title": "Бензин АИ-92", "quantity": 40, "unit": "л"}],
        project_id=project.id,
    )
    session.commit()

    says(client, "/templates")
    codes = buttons(telegram_box)
    assert codes and codes[0].startswith("t:")

    presses(client, codes[0])
    assert "Проверьте заявку" in last(telegram_box)
    assert "Бензин АИ-92 — 40 л" in last(telegram_box)


def test_foreign_template_is_not_applied(client, session, employee, manager, telegram_box) -> None:
    from app.services import templates as tsvc

    linked(session, employee)
    foreign = tsvc.create(
        session,
        manager,
        name="Чужой шаблон",
        lines=[{"title": "Что-то", "quantity": 1, "unit": "шт."}],
    )
    session.commit()

    presses(client, f"t:{foreign.id}")
    assert "Такого шаблона нет" in last(telegram_box)


# --- Заявка только от себя ---------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Создай заявку за Иванова",
        "оформи заявку от имени Петрова",
        "нужен цемент вместо Сидорова",
    ],
)
def test_request_for_someone_else_is_refused(
    client, session, employee, telegram_box, text
) -> None:
    """Через бота заявку подают только от своего имени."""
    linked(session, employee)
    says(client, text)
    assert last(telegram_box) == (
        "Через Telegram заявку можно оформить только от вашего имени."
    )
    assert session.scalars(select(ExpenseRequest)).all() == []


def test_refusal_works_inside_the_dialogue(
    client, session, employee, project, assistant_box, telegram_box
) -> None:
    """И посреди разговора тоже — а к модели за этим не ходим."""
    linked(session, employee)
    says(client, "/new")
    presses(client, f"p:{project.id}")

    says(client, "заявку за Иванова: два мешка цемента")
    assert "только от вашего имени" in last(telegram_box)
    assert assistant_box.prompts == []
    assert session.scalars(select(ExpenseRequest)).all() == []


def test_created_request_belongs_to_the_sender(
    client, session, employee, manager, project, assistant_box, telegram_box
) -> None:
    """Автор — владелец чата, а не тот, кого назвали в тексте."""
    linked(session, employee)
    assistant_box.answer = REPLY_READY
    says(client, "/new")
    presses(client, f"p:{project.id}")
    says(client, "два мешка цемента")
    presses(client, "send")

    (request,) = session.scalars(select(ExpenseRequest)).all()
    assert request.employee_id == employee.id
    assert request.employee_id != manager.id
