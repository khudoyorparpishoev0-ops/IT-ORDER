"""История действий по заявке.

Проверяется не «функция вызвалась», а обещание, которое история даёт
человеку: по ней видно, кто что сделал и что именно изменилось, подделать
запись нельзя, а просмотры не превращают ленту в шум.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.db.models import EventKind, RequestView
from app.services import requests as svc


def _create(client, employee, project, **extra) -> dict:
    payload = {
        "employee_id": employee.id,
        "project_id": project.id,
        "lines": [{"title": "Кабель UTP Cat6", "quantity": 2, "unit": "бухта"}],
        "submit": False,
    }
    payload.update(extra)
    response = client.post("/api/requests", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _events(card: dict, kind: str) -> list[dict]:
    return [e for e in card["events"] if e["kind"] == kind]


# --- кто сделал -------------------------------------------------------


def test_event_records_who_did_it(client, login, employee, project, session):
    """У события есть не только имя строкой, но и ссылка на сотрудника."""
    login(employee)
    card = _create(client, employee, project)

    request = svc.get_request(session, card["id"], full=True)
    created = [e for e in request.events if e.kind is EventKind.CREATED][0]
    assert created.employee_id == employee.id
    assert created.actor_type == "human"
    assert created.actor == employee.full_name


def test_actor_from_session_not_from_body(
    client, login, employee, manager, project, session
):
    """Автор события — тот, кто вошёл, а не тот, кого назвали в теле.

    Иначе достаточно подменить одно поле, чтобы решение руководителя в
    истории выглядело чужим — или чтобы своё приписать другому.
    """
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})

    login(manager)
    response = client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": True, "actor": "Кто-то другой"},
    )
    assert response.status_code == 200, response.text

    request = svc.get_request(session, card["id"], full=True)
    approved = [e for e in request.events if e.kind is EventKind.NEED_APPROVED][0]
    assert approved.employee_id == manager.id
    assert approved.actor_role == manager.role.value
    assert "Кто-то другой" not in approved.actor
    assert approved.actor == manager.full_name


def test_history_has_no_edit_or_delete_endpoint(client, login, employee, project):
    """Историю нельзя ни исправить, ни стереть через API.

    В этом весь смысл истории: запись, которую можно поправить задним
    числом, ничего не доказывает.
    """
    login(employee)
    card = _create(client, employee, project)
    base = f"/api/requests/{card['id']}"
    for response, where in (
        (client.patch(f"{base}/events/1", json={"text": "подделка"}), "patch"),
        (client.delete(f"{base}/events/1"), "delete"),
        (client.post(f"{base}/events", json={"text": "подделка"}), "post"),
    ):
        assert response.status_code in (404, 405), f"{where}: {response.status_code}"


# --- что именно изменилось --------------------------------------------


def test_draft_edit_records_before_and_after(client, login, employee, project, session):
    """Правка черновика пишет, что добавили, что убрали и что изменили."""
    login(employee)
    card = _create(client, employee, project)

    response = client.patch(
        f"/api/requests/{card['id']}",
        json={
            "lines": [
                {"title": "Кабель UTP Cat6", "quantity": 5, "unit": "бухта"},
                {"title": "Гофра 16 мм", "quantity": 10, "unit": "м"},
            ]
        },
    )
    assert response.status_code == 200, response.text

    request = svc.get_request(session, card["id"], full=True)
    edited = [e for e in request.events if e.kind is EventKind.EDITED]
    assert len(edited) == 1
    details = edited[0].details
    assert [item["title"] for item in details["added"]] == ["Гофра 16 мм"]
    assert details["changed"][0]["title"] == "Кабель UTP Cat6"
    assert details["changed"][0]["from"] == "2 бухта"
    assert details["changed"][0]["to"] == "5 бухта"
    assert "removed" not in details


def test_removed_line_is_recorded(client, login, employee, project, session):
    login(employee)
    card = _create(
        client,
        employee,
        project,
        lines=[
            {"title": "Кабель UTP Cat6", "quantity": 2, "unit": "бухта"},
            {"title": "Гофра 16 мм", "quantity": 10, "unit": "м"},
        ],
    )
    client.patch(
        f"/api/requests/{card['id']}",
        json={"lines": [{"title": "Кабель UTP Cat6", "quantity": 2, "unit": "бухта"}]},
    )
    request = svc.get_request(session, card["id"], full=True)
    details = [e for e in request.events if e.kind is EventKind.EDITED][0].details
    assert [item["title"] for item in details["removed"]] == ["Гофра 16 мм"]


def test_edit_without_changes_writes_nothing(client, login, employee, project, session):
    """Открыл, ничего не поменял, сохранил — в истории пусто.

    Событие «изменил» без изменений превращает ленту в шум и учит её не
    читать.
    """
    login(employee)
    card = _create(client, employee, project)
    client.patch(
        f"/api/requests/{card['id']}",
        json={"lines": [{"title": "Кабель UTP Cat6", "quantity": 2, "unit": "бухта"}]},
    )
    request = svc.get_request(session, card["id"], full=True)
    assert [e for e in request.events if e.kind is EventKind.EDITED] == []


def test_project_change_is_recorded(client, login, employee, project, session):
    from app.db.models import Project

    other = Project(name="Второй объект")
    session.add(other)
    session.flush()

    login(employee)
    card = _create(client, employee, project)
    client.patch(f"/api/requests/{card['id']}", json={"project_id": other.id})

    request = svc.get_request(session, card["id"], full=True)
    details = [e for e in request.events if e.kind is EventKind.EDITED][0].details
    assert details["project"] == {"from": project.name, "to": "Второй объект"}


def test_status_transition_records_from_and_to(
    client, login, employee, manager, project, session
):
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})

    request = svc.get_request(session, card["id"], full=True)
    submitted = [e for e in request.events if e.kind is EventKind.SUBMITTED][0]
    assert submitted.details["status"] == {"from": "draft", "to": "pending"}
    assert submitted.details["waiting"], "видно, кто может взять заявку дальше"
    assert submitted.details["holder"] == "У руководителя: согласовать покупку"


def test_pricing_records_amount_before_and_after(
    client, login, employee, manager, procurement, project, session, pipeline
):
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    pipeline(
        card["id"],
        manager=manager,
        buyer=procurement,
        prices={"Кабель UTP Cat6": "1200.00"},
        to="priced",
    )

    request = svc.get_request(session, card["id"], full=True)
    priced = [e for e in request.events if e.kind is EventKind.PRICED][0]
    assert priced.details["amount"]["from"].startswith("0,00")
    assert priced.details["amount"]["to"].replace("\xa0", " ").startswith("2 400")
    assert priced.details["status"] == {"from": "sourcing", "to": "priced"}


def test_payment_records_method_and_document(
    client, login, employee, manager, finance, procurement, project, session, pipeline
):
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    pipeline(
        card["id"],
        manager=manager,
        buyer=procurement,
        prices={"Кабель UTP Cat6": "1200.00"},
        to="approved",
    )
    login(finance)
    response = client.post(
        f"/api/requests/{card['id']}/payment",
        json={"method": "card", "document": "ПП-77"},
    )
    assert response.status_code == 200, response.text

    request = svc.get_request(session, card["id"], full=True)
    paid = [e for e in request.events if e.kind is EventKind.PAID][0]
    assert paid.details["document"] == "ПП-77"
    # Ключ `amount` зарезервирован за парой «было → стало»: итоговую
    # сумму шага панель ждёт отдельным ключом и рисует её иначе.
    assert "amount" not in paid.details
    assert paid.details["amount_total"].replace("\xa0", " ").startswith("2 400")
    assert paid.details["method"] == "card"
    assert paid.details["status"]["to"] == "paid"
    assert paid.employee_id == finance.id


def test_rejection_records_comment(
    client, login, employee, manager, project, session
):
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})

    login(manager)
    client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": False, "comment": "Есть на складе"},
    )
    request = svc.get_request(session, card["id"], full=True)
    rejected = [e for e in request.events if e.kind is EventKind.REJECTED][0]
    assert rejected.details["comment"] == "Есть на складе"
    assert rejected.details["status"] == {"from": "pending", "to": "rejected"}


def test_details_carry_no_secrets(client, login, employee, project, session):
    """В подробностях события не должно быть паролей и токенов.

    Проверка тупая намеренно: история читается людьми и выгружается, и
    цена ошибки здесь — утечка, а не косметика.
    """
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})

    request = svc.get_request(session, card["id"], full=True)
    dump = " ".join(str(e.details) + e.text for e in request.events).lower()
    for word in ("password", "пароль", "token", "secret", "hash", "argon2", "totp"):
        assert word not in dump


# --- кто открывал ------------------------------------------------------


def test_view_is_recorded_once(client, login, employee, project, session):
    login(employee)
    card = _create(client, employee, project)

    for _ in range(3):
        response = client.post(f"/api/requests/{card['id']}/viewed")
        assert response.status_code == 204, response.text

    from sqlalchemy import select

    views = session.scalars(select(RequestView)).all()
    assert [v.times for v in views] == [1], "возвращения в пределах получаса — один просмотр"


def test_view_counts_again_after_window(client, login, employee, project, session):
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/viewed")

    from sqlalchemy import select

    row = session.scalars(select(RequestView)).one()
    row.last_viewed_at = utcnow() - svc.VIEW_WINDOW - timedelta(minutes=1)
    session.flush()

    client.post(f"/api/requests/{card['id']}/viewed")
    session.refresh(row)
    assert row.times == 2


def test_viewers_show_up_in_the_card(
    client, login, employee, manager, project
):
    """Автор видит, что заявку открыли, а не только что она в очереди."""
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})

    login(manager)
    client.post(f"/api/requests/{card['id']}/viewed")

    login(employee)
    card = client.get(f"/api/requests/{card['id']}").json()
    names = [v["employee_name"] for v in card["viewers"]]
    assert manager.full_name in names
    seen = next(v for v in card["viewers"] if v["employee_name"] == manager.full_name)
    assert seen["times"] == 1
    assert "." in seen["last_viewed_at"]


def test_view_does_not_pollute_the_timeline(client, login, employee, project, session):
    """Просмотр не становится событием: их десятки, и лента бы утонула."""
    login(employee)
    card = _create(client, employee, project)
    before = len(svc.get_request(session, card["id"], full=True).events)
    for _ in range(5):
        client.post(f"/api/requests/{card['id']}/viewed")
    after = len(svc.get_request(session, card["id"], full=True).events)
    assert after == before


def test_foreign_request_cannot_be_marked_viewed(
    client, login, employee, manager, project, session
):
    """Чужую заявку не отметить — и ответ такой же, как у несуществующей."""
    login(manager)
    card = _create(client, manager, project)

    login(employee)
    response = client.post(f"/api/requests/{card['id']}/viewed")
    assert response.status_code == 404


def test_view_endpoint_needs_login(client, employee, project, login):
    login(employee)
    card = _create(client, employee, project)
    client.post("/api/auth/logout")
    response = client.post(f"/api/requests/{card['id']}/viewed")
    assert response.status_code == 401


def test_viewer_list_has_no_ip_or_user_agent(client, login, employee, project):
    """IP и user-agent сотрудникам не показываем: они ничего не объясняют,
    а собирать их «на всякий случай» — это слежка, а не история."""
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/viewed")
    card = client.get(f"/api/requests/{card['id']}").json()
    assert card["viewers"]
    for viewer in card["viewers"]:
        assert set(viewer) == {
            "employee_id",
            "employee_name",
            "role",
            "first_viewed_at",
            "last_viewed_at",
            "first_viewed_iso",
            "times",
        }


# --- у каждого события есть человек ------------------------------------


def test_every_step_names_the_person_who_did_it(
    client, login, employee, manager, procurement, finance, project, session, pipeline
):
    """Главное обещание журнала: по каждой строке видно, кто её сделал.

    Проверяется весь путь заявки разом. Если хотя бы один шаг остался
    без имени и роли, читатель журнала не сможет понять, к кому идти, —
    а ради этого журнал и открывают.
    """
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    pipeline(
        card["id"],
        manager=manager,
        buyer=procurement,
        prices={"Кабель UTP Cat6": "1200.00"},
        to="approved",
    )
    login(finance)
    client.post(
        f"/api/requests/{card['id']}/payment",
        json={"method": "cash", "document": "РКО-9"},
    )

    request = svc.get_request(session, card["id"], full=True)
    expected = {
        EventKind.CREATED: employee,
        EventKind.SUBMITTED: employee,
        EventKind.NEED_APPROVED: manager,
        EventKind.PRICED: procurement,
        EventKind.APPROVED: manager,
        EventKind.PAID: finance,
    }
    by_kind = {e.kind: e for e in request.events}
    for kind, person in expected.items():
        event = by_kind.get(kind)
        assert event is not None, f"нет события {kind.value}"
        assert event.employee_id == person.id, f"{kind.value}: не тот сотрудник"
        assert event.actor_role == person.role.value, f"{kind.value}: нет роли"
        assert event.actor == person.full_name, f"{kind.value}: нет имени"


def test_decision_and_handover_are_separate_events(
    client, login, employee, manager, procurement, project, session
):
    """«Одобрил» и «передала дальше» — два разных дела.

    Одной строкой «Потребность одобрена, заявка передана в отдел закупа»
    получалось, что маршрут выбрал руководитель. Он решение принял, а
    маршрут выбрала система, и по ленте это должно быть видно.
    """
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})

    request = svc.get_request(session, card["id"], full=True)
    human = [e for e in request.events if e.kind is EventKind.NEED_APPROVED][0]
    system = [e for e in request.events if e.kind is EventKind.SOURCING][0]

    assert human.actor_type == "human"
    assert human.employee_id == manager.id
    assert system.actor_type == "system"
    assert system.employee_id is None, "у системы нет сотрудника"
    assert system.actor_role is None
    assert human.created_at <= system.created_at, "сначала решение, потом маршрут"
    assert system.details["waiting"], "видно, кто может взять заявку дальше"


def test_system_event_has_no_borrowed_name(
    client, login, employee, manager, project, session
):
    """Системный переход не подписывается именем человека."""
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})

    request = svc.get_request(session, card["id"], full=True)
    system = [e for e in request.events if e.actor_type == "system"]
    assert system
    for event in system:
        assert event.actor != manager.full_name


def test_role_is_a_snapshot_not_a_link(
    client, login, employee, manager, project, session
):
    """Роль в событии — та, что была в момент действия.

    Закупщика переведут в руководители, и «Оценил заявку · Руководитель»
    станет неправдой про уже случившееся.
    """
    from app.db.models import EmployeeRole

    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})

    manager.role = EmployeeRole.EMPLOYEE
    session.flush()

    request = svc.get_request(session, card["id"], full=True)
    approved = [e for e in request.events if e.kind is EventKind.NEED_APPROVED][0]
    assert approved.actor_role == "manager", "роль зафиксирована на момент действия"


def test_procurement_price_change_is_visible_per_line(
    client, login, employee, manager, procurement, project, session, pipeline
):
    """Видно, что стало с ценой каждой позиции: «не оценена» → сумма."""
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    pipeline(
        card["id"],
        manager=manager,
        buyer=procurement,
        prices={"Кабель UTP Cat6": "1200.00"},
        to="priced",
    )
    request = svc.get_request(session, card["id"], full=True)
    priced = [e for e in request.events if e.kind is EventKind.PRICED][0]
    line = priced.details["prices"][0]
    assert line["title"] == "Кабель UTP Cat6"
    assert line["from"] == "не оценена"
    assert line["to"].replace("\xa0", " ").startswith("1 200")


def test_comment_keeps_author_role_and_stage(
    client, login, employee, manager, procurement, project, session, pipeline
):
    """У комментария есть автор, его роль и этап.

    Через месяц «Ив» без этапа не значит ничего, а «на оценке закупа» —
    значит.
    """
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})

    login(procurement)
    detail = client.get(f"/api/requests/{card['id']}").json()
    client.post(
        f"/api/requests/{card['id']}/sourcing",
        json={
            "lines": [
                {"id": detail["lines"][0]["id"], "price": "1200.00", "from_stock": False}
            ],
            "comment": "Беру у проверенного поставщика",
        },
    )

    request = svc.get_request(session, card["id"], full=True)
    comment = [e for e in request.events if e.kind is EventKind.COMMENTED][0]
    assert comment.details["comment"] == "Беру у проверенного поставщика"
    assert comment.details["stage"] == "На оценке закупа"
    assert comment.employee_id == procurement.id
    assert comment.actor_role == procurement.role.value


def test_rejection_reason_stays_in_the_rejection(
    client, login, employee, manager, project, session
):
    """Причина отказа живёт в самом отказе, а не отдельной строкой.

    Второе событие с тем же текстом удвоило бы одну и ту же мысль, а
    читатель ленты решил бы, что руководитель написал дважды.
    """
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    login(manager)
    client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": False, "comment": "Есть на складе"},
    )
    request = svc.get_request(session, card["id"], full=True)
    rejected = [e for e in request.events if e.kind is EventKind.REJECTED][0]
    assert rejected.details["comment"] == "Есть на складе"
    assert rejected.details["stage"]
    assert rejected.employee_id == manager.id
    assert rejected.actor_role == manager.role.value
    assert [e for e in request.events if e.kind is EventKind.COMMENTED] == []


def test_admin_creating_for_another_is_recorded_as_admin(
    client, login, admin, employee, project, session
):
    """Заявку завёл администратор — так и записано, автор отдельно.

    «Создал Иванов» было бы неправдой: Иванов в этот момент мог быть на
    объекте без связи.
    """
    login(admin)
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Гофра 16 мм", "quantity": 5, "unit": "м"}],
            "submit": False,
        },
    )
    assert response.status_code == 201, response.text
    request = svc.get_request(session, response.json()["id"], full=True)
    created = [e for e in request.events if e.kind is EventKind.CREATED][0]
    assert created.employee_id == admin.id
    assert created.details["author"] == employee.full_name


# --- кто ждёт и видел ли -----------------------------------------------


def test_waiting_people_show_whether_they_opened_it(
    client, login, employee, manager, project
):
    """«У руководителя третий день» и «...и туда никто не заходил» —
    разные новости, и карточка должна их различать."""
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})

    body = client.get(f"/api/requests/{card['id']}").json()
    watch = {w["full_name"]: w for w in body["awaiting_watch"]}
    assert manager.full_name in watch
    assert watch[manager.full_name]["viewed_at"] is None
    assert watch[manager.full_name]["role"] == manager.role.value

    login(manager)
    client.post(f"/api/requests/{card['id']}/viewed")
    body = client.get(f"/api/requests/{card['id']}").json()
    watch = {w["full_name"]: w for w in body["awaiting_watch"]}
    assert watch[manager.full_name]["viewed_at"] is not None
    assert watch[manager.full_name]["times"] == 1


def test_author_is_not_in_the_waiting_list(
    client, login, employee, manager, project, session
):
    """Свою заявку человек не согласует — значит, и ждать её не может."""
    login(manager)
    card = _create(client, manager, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    body = client.get(f"/api/requests/{card['id']}").json()
    assert manager.full_name not in [w["full_name"] for w in body["awaiting_watch"]]


# --- сколько где стояла -------------------------------------------------


def test_stays_show_where_the_request_stood(
    client, login, employee, manager, project, session
):
    """Видно, сколько заявка провела на каждом шаге."""
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})

    body = client.get(f"/api/requests/{card['id']}").json()
    stages = [s["stage"] for s in body["stays"]]
    assert stages == ["draft", "pending", "sourcing"]
    assert body["stays"][-1]["ongoing"] is True, "на последнем шаге заявка стоит сейчас"
    assert all(s["hours"] >= 0 for s in body["stays"])
    assert body["stays"][-1]["holder"] == "У отдела закупа: склад и цены"


def test_closed_request_has_no_ongoing_stay(
    client, login, employee, manager, procurement, finance, project, pipeline
):
    """Закрытая заявка нигде не стоит: последний отрезок не «идёт»."""
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    pipeline(
        card["id"],
        manager=manager,
        buyer=procurement,
        prices={"Кабель UTP Cat6": "1200.00"},
        to="approved",
    )
    login(finance)
    client.post(
        f"/api/requests/{card['id']}/payment",
        json={"method": "cash", "document": "РКО-5"},
    )
    body = client.get(f"/api/requests/{card['id']}").json()
    assert body["stays"], "отрезки посчитаны"
    assert not any(s["ongoing"] for s in body["stays"])


# --- старые записи ------------------------------------------------------


def test_old_events_without_actor_survive(client, login, employee, project, session):
    """Записи, сделанные до появления истории, продолжают показываться.

    У них нет ни ссылки на сотрудника, ни роли — только имя строкой. Это
    и показываем: выдумывать сотрудника задним числом нельзя.
    """
    from app.db.models import RequestEvent

    login(employee)
    card = _create(client, employee, project)
    request = svc.get_request(session, card["id"], full=True)
    request.events.append(
        RequestEvent(
            kind=EventKind.COMMENTED,
            text="Старая запись",
            actor="ПЁТР СТАРЫЙ",
            employee_id=None,
            actor_role=None,
            details={},
        )
    )
    session.flush()

    body = client.get(f"/api/requests/{card['id']}").json()
    old = [e for e in body["events"] if e["text"] == "Старая запись"][0]
    assert old["actor"] == "ПЁТР СТАРЫЙ"
    assert old["actor_id"] is None
    assert old["actor_role"] is None
    assert old["actor_type"] == "human"


def test_comment_comes_before_the_handover(
    client, login, employee, manager, procurement, project, session
):
    """Комментарий стоит после решения и до перехода.

    Иначе в ленте выходит, что руководитель написал вслед уже ушедшей
    заявке, — а он написал, когда решал.
    """
    login(employee)
    card = _create(client, employee, project)
    client.post(f"/api/requests/{card['id']}/submit", json={})
    login(manager)
    client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": True, "comment": "Берите у постоянного поставщика"},
    )

    request = svc.get_request(session, card["id"], full=True)
    order = [e.kind for e in request.events]
    assert order.index(EventKind.NEED_APPROVED) < order.index(EventKind.COMMENTED)
    assert order.index(EventKind.COMMENTED) < order.index(EventKind.SOURCING)
