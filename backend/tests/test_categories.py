"""Категории расхода: своя форма и свой маршрут у каждого вида.

Главное, что здесь проверяется: форма соответствует расходу, сумму
считает сервер, а обойти проверки прямым запросом к API нельзя.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.models import ExpenseRequest, RequestCategory, RequestStatus
from app.services import categories as cat
from app.services import requests as svc


def _create(client, employee, project, category, details=None, lines=None, submit=False):
    payload = {
        "employee_id": employee.id,
        "project_id": project.id,
        "category": category,
        "submit": submit,
    }
    if details is not None:
        payload["details"] = details
    if lines is not None:
        payload["lines"] = lines
    return client.post("/api/requests", json=payload)


# --- расчёты -------------------------------------------------------------


def test_meals_multiply_people_days_and_rate() -> None:
    """Четверо, два дня, 50 на человека — 400, а не «Обед · 1 шт.»."""
    amount = cat.amount_of(
        RequestCategory.MEALS, {"people": 4, "days": 2, "rate": "50.00"}
    )
    assert amount == Decimal("400.00")
    assert isinstance(amount, Decimal), "деньги только Decimal, никакого float"


def test_cargo_sums_freight_customs_and_extra() -> None:
    amount = cat.amount_of(
        RequestCategory.CARGO, {"cargo_cost": "1500.00", "customs": "400.00"}
    )
    assert amount == Decimal("1900.00")


def test_trip_sums_all_articles() -> None:
    amount = cat.amount_of(
        RequestCategory.TRIP,
        {"transport": "300.00", "per_diem": "450.00", "other": "100.00"},
    )
    assert amount == Decimal("850.00")


def test_lodging_counts_nights_not_days() -> None:
    """С 11 по 14 — три ночи, а не четыре дня: платят за ночи."""
    details = {"check_in": "2026-09-11", "check_out": "2026-09-14", "nightly_rate": "120.00"}
    assert cat.nights_of(details) == 3
    assert cat.amount_of(RequestCategory.LODGING, details) == Decimal("360.00")


def test_lodging_multiplies_by_rooms() -> None:
    details = {
        "check_in": "2026-09-11",
        "check_out": "2026-09-14",
        "nightly_rate": "120.00",
        "rooms": 2,
    }
    assert cat.amount_of(RequestCategory.LODGING, details) == Decimal("720.00")


def test_trip_days_count_both_ends() -> None:
    """С 11 по 13 — три дня: выехали, работали, вернулись."""
    assert cat.days_of({"date_from": "2026-09-11", "date_to": "2026-09-13"}) == 3


def test_money_never_becomes_float() -> None:
    """Копейки не теряются: 0.1 + 0.2 у float даёт 0.30000000000000004."""
    amount = cat.amount_of(
        RequestCategory.TRIP, {"transport": "0.10", "lodging": "0.20"}
    )
    assert amount == Decimal("0.30")


# --- проверка полей ------------------------------------------------------


def test_required_fields_are_named_all_at_once() -> None:
    """Человек должен увидеть все незаполненные поля разом, а не по одному."""
    problems = cat.validate(RequestCategory.FUEL, {})
    assert len(problems) == 3
    assert any("Автомобиль" in p for p in problems)
    assert any("Вид расхода" in p for p in problems)
    assert any("Сумма" in p for p in problems)


def test_zero_quantity_is_rejected() -> None:
    problems = cat.validate(
        RequestCategory.MEALS, {"meal_type": "Обед", "people": 0, "days": 2}
    )
    assert any("Человек" in p for p in problems)


def test_negative_amount_is_rejected() -> None:
    """Минус в смете означал бы возврат, а возвратов в ORDER нет."""
    problems = cat.validate(
        RequestCategory.FUEL,
        {"vehicle": "Opel", "kind": "Бензин", "amount": "-150.00"},
    )
    assert any("отрицательной" in p for p in problems)


def test_end_date_before_start_is_rejected() -> None:
    problems = cat.validate(
        RequestCategory.TRIP,
        {
            "staff": "Иванов",
            "destination": "Регар",
            "purpose": "Монтаж",
            "date_from": "2026-09-13",
            "date_to": "2026-09-11",
        },
    )
    assert any("раньше начала" in p for p in problems)


def test_every_category_has_a_spec() -> None:
    """Новая категория без описания формы — заявка, которую не подать."""
    missing = [c.value for c in RequestCategory if c not in cat.SPECS]
    assert missing == []


# --- заявка каждого вида через API ---------------------------------------


def test_materials_keep_the_estimate_form(client, login, employee, project):
    """Материалы по-прежнему подаются сметой: что, сколько и в чём."""
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "MATERIALS",
        lines=[{"title": "Кабель UTP Cat6", "quantity": 2, "unit": "бухта"}],
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["lines"][0]["unit"] == "бухта"
    assert card["priced"] is False, "цену назовёт закуп"


def test_meals_need_no_unit_at_all(client, login, employee, project, session):
    """У питания нет ни «шт.», ни наименования — есть люди и дни."""
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "MEALS",
        details={"meal_type": "Обед и ужин", "people": 4, "days": 2, "rate": "50.00"},
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["amount"] == "400.00"
    line = card["lines"][0]
    assert line["title"] == "Обед и ужин"
    assert line["quantity"] == 8
    assert line["unit"] == "чел.-дн."


def test_trip_records_route_and_dates(client, login, employee, project):
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "TRIP",
        details={
            "staff": "Иванов, Петров, Сидоров",
            "destination": "Душанбе → Регар",
            "purpose": "Монтаж узла связи",
            "date_from": "2026-09-11",
            "date_to": "2026-09-13",
            "transport": "300.00",
            "per_diem": "450.00",
            "other": "100.00",
        },
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["amount"] == "850.00"
    assert card["lines"][0]["quantity"] == 3, "три дня"
    assert dict(card["details_summary"])["Куда"] == "Душанбе → Регар"


def test_delivery_records_where_from_and_where_to(client, login, employee, project):
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "DELIVERY",
        details={
            "from_place": "Ориён-Медиа",
            "to_place": "Асри Нав",
            "what": "Жёсткий диск",
            "amount": "30.00",
        },
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["amount"] == "30.00"
    assert "Ориён-Медиа → Асри Нав" in card["lines"][0]["title"]


def test_cargo_records_weight_and_customs(client, login, employee, project):
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "CARGO",
        details={
            "from_country": "Китай",
            "to_city": "Душанбе",
            "what": "Оборудование Hikvision",
            "weight_kg": 120,
            "cargo_cost": "1500.00",
            "customs": "400.00",
        },
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["amount"] == "1900.00"
    assert dict(card["details_summary"])["Вес"] == "120 кг"


def test_fuel_records_litres_and_vehicle(client, login, employee, project):
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "FUEL",
        details={
            "vehicle": "Opel",
            "kind": "Бензин",
            "liters": 20,
            "amount": "150.00",
            "route": "Регар",
        },
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["amount"] == "150.00"
    assert card["lines"][0]["unit"] == "л"
    assert card["lines"][0]["quantity"] == 20


def test_service_can_be_filed_without_a_price(client, login, employee, project):
    """Сумму назовёт закуп — это разрешено и описано в форме."""
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "SERVICES",
        details={"service": "Чистка офиса", "description": "Раз в неделю, два часа"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["priced"] is False


def test_lodging_request(client, login, employee, project):
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "LODGING",
        details={
            "staff": "Иванов, Петров",
            "city": "Худжанд",
            "hotel": "Согд",
            "check_in": "2026-09-11",
            "check_out": "2026-09-14",
            "rooms": 2,
            "nightly_rate": "120.00",
        },
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["amount"] == "720.00"
    assert dict(card["details_summary"])["Ночей"] == "3"


def test_connectivity_request(client, login, employee, project):
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "CONNECTIVITY",
        details={
            "service_kind": "Хостинг",
            "account": "sofo-hotel.tj",
            "period": "1 год",
            "amount": "271.00",
        },
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["amount"] == "271.00"
    assert "sofo-hotel.tj" in card["lines"][0]["title"]


def test_other_request_requires_a_reason(client, login, employee, project):
    login(employee)
    response = _create(
        client, employee, project, "OTHER", details={"description": "Ключи от щитовой"}
    )
    assert response.status_code == 422, "без обоснования «прочее» не подаётся"

    response = _create(
        client,
        employee,
        project,
        "OTHER",
        details={
            "description": "Ключи от щитовой",
            "reason": "Старые потеряны, доступ нужен ежедневно",
            "amount": "40.00",
        },
    )
    assert response.status_code == 201, response.text


# --- маршрут зависит от категории ----------------------------------------


def test_materials_go_through_procurement(
    client, login, employee, manager, procurement, project, session
):
    """Материалы: руководитель одобряет покупку, цену называет закуп."""
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "MATERIALS",
        lines=[{"title": "Кабель UTP Cat6", "quantity": 2, "unit": "бухта"}],
        submit=True,
    ).json()

    login(manager)
    response = client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "sourcing", "ушла в закуп"


def test_meals_skip_procurement(client, login, employee, manager, project, session):
    """Питание с известной суммой идёт сразу в бухгалтерию.

    Закупу там нечего делать: склад не проверишь, счёт уже выставлен.
    """
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "MEALS",
        details={"meal_type": "Обед", "people": 4, "days": 2, "rate": "50.00"},
        submit=True,
    ).json()

    login(manager)
    response = client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved", "минуя закуп"
    assert body["amount"] == "400.00"


def test_service_without_price_goes_to_procurement(
    client, login, employee, manager, procurement, project
):
    """Сумма не названа — кто-то должен её назвать, и это закуп.

    Иначе заявка дошла бы до бухгалтерии с нулём, а платить по нулю
    нельзя.
    """
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "SERVICES",
        details={"service": "Чистка офиса", "description": "Раз в неделю"},
        submit=True,
    ).json()

    login(manager)
    body = client.post(
        f"/api/requests/{card['id']}/decision", json={"approve": True}
    ).json()
    assert body["status"] == "sourcing"


def test_service_with_price_skips_procurement(client, login, employee, manager, project):
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "SERVICES",
        details={
            "service": "Чистка офиса",
            "description": "Раз в неделю",
            "amount": "72.00",
        },
        submit=True,
    ).json()

    login(manager)
    body = client.post(
        f"/api/requests/{card['id']}/decision", json={"approve": True}
    ).json()
    assert body["status"] == "approved"
    assert body["amount"] == "72.00"


def test_cargo_goes_through_procurement_even_with_a_price(
    client, login, employee, manager, procurement, project
):
    """Карго оценивает закуп: у автора прикидка, у закупа счёт."""
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "CARGO",
        details={
            "from_country": "Китай",
            "to_city": "Душанбе",
            "what": "Оборудование",
            "cargo_cost": "1500.00",
        },
        submit=True,
    ).json()

    login(manager)
    body = client.post(
        f"/api/requests/{card['id']}/decision", json={"approve": True}
    ).json()
    assert body["status"] == "sourcing"


def test_direct_route_reaches_payment(
    client, login, employee, manager, finance, project
):
    """Питание доходит до оплаты в два шага, а не в четыре."""
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "liters": 20, "amount": "150.00"},
        submit=True,
    ).json()

    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})
    login(finance)
    response = client.post(
        f"/api/requests/{card['id']}/payment",
        json={"method": "cash", "document": "РКО-15"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paid"


# --- обойти форму запросом нельзя ----------------------------------------


def test_lines_cannot_be_smuggled_into_a_typed_category(
    client, login, employee, project
):
    """Питание сметой «Обед · 1 шт.» не подать даже прямым запросом.

    Ровно ради этого всё и затевалось: форма обязана соответствовать
    расходу, и решает это сервер, а не панель.
    """
    login(employee)
    response = _create(
        client,
        employee,
        project,
        "MEALS",
        lines=[{"title": "Обед", "quantity": 1, "unit": "шт."}],
    )
    assert response.status_code == 422
    assert "Тип питания" in response.text


def test_details_cannot_replace_the_estimate(client, login, employee, project):
    """И наоборот: материалы полями категории не подать."""
    login(employee)
    response = _create(
        client, employee, project, "MATERIALS", details={"people": 4, "days": 2}
    )
    assert response.status_code == 422
    assert "ни одной строки" in response.text


def test_amount_from_the_client_is_ignored(client, login, employee, project):
    """Сумму считает сервер по полям, а не берёт из запроса."""
    login(employee)
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "category": "MEALS",
            "amount": "999999.00",
            "details": {"meal_type": "Обед", "people": 2, "days": 1, "rate": "40.00"},
            "submit": False,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["amount"] == "80.00"


def test_procurement_flag_cannot_be_sent_by_the_client(
    client, login, employee, manager, project
):
    """Маршрут не выбирается запросом: его задаёт категория."""
    login(employee)
    card = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "category": "MATERIALS",
            "requires_procurement": False,
            "lines": [{"title": "Цемент М500", "quantity": 5, "unit": "мешок"}],
            "submit": True,
        },
    ).json()

    login(manager)
    body = client.post(
        f"/api/requests/{card['id']}/decision", json={"approve": True}
    ).json()
    assert body["status"] == "sourcing", "материалы всё равно идут через закуп"


def test_employee_still_sees_only_own_typed_requests(
    client, login, employee, manager, project
):
    """Права категориями не расширяются: чужая заявка — 404."""
    login(manager)
    card = _create(
        client,
        manager,
        project,
        "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    ).json()

    login(employee)
    assert client.get(f"/api/requests/{card['id']}").status_code == 404


def test_categories_endpoint_needs_login(client):
    assert client.get("/api/requests/categories").status_code == 401


def test_categories_endpoint_describes_the_route(client, login, employee):
    login(employee)
    body = client.get("/api/requests/categories").json()
    by_code = {item["code"]: item for item in body}
    assert by_code["MATERIALS"]["route"] == [
        "Автор",
        "Руководитель",
        "Отдел закупа",
        "Согласование суммы",
        "Бухгалтерия",
        "Оплачено",
    ]
    assert by_code["MEALS"]["route"] == ["Автор", "Руководитель", "Бухгалтерия", "Оплачено"]
    assert by_code["MEALS"]["requires_unit"] is False
    assert [f["key"] for f in by_code["MEALS"]["fields"]] == [
        "meal_type",
        "people",
        "days",
        "rate",
    ]


# --- старые заявки --------------------------------------------------------


def test_request_without_category_works_as_before(
    client, login, employee, manager, procurement, project
):
    """Заявка без категории идёт прежним путём — сметой через закуп."""
    login(employee)
    card = _create(
        client,
        employee,
        project,
        None,
        lines=[{"title": "Цемент М500", "quantity": 5, "unit": "мешок"}],
        submit=True,
    ).json()
    assert card["category"] is None
    assert card["details"] == {}

    login(manager)
    body = client.post(
        f"/api/requests/{card['id']}/decision", json={"approve": True}
    ).json()
    assert body["status"] == "sourcing"


def test_old_request_without_details_opens(client, login, employee, project, session):
    """У заявок старше миграции подробностей нет — карточка это переживает."""
    login(employee)
    card = _create(
        client,
        employee,
        project,
        None,
        lines=[{"title": "Цемент М500", "quantity": 5, "unit": "мешок"}],
    ).json()

    row = session.get(ExpenseRequest, card["id"])
    row.details = {}
    row.category = None
    session.flush()

    body = client.get(f"/api/requests/{card['id']}").json()
    assert body["details_summary"] == []
    assert body["lines"][0]["title"] == "Цемент М500"


def test_draft_can_change_its_category(client, login, employee, project):
    """Ошиблись категорией — правится, состав пересобирается по новой форме."""
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "MEALS",
        details={"meal_type": "Обед", "people": 2, "days": 1, "rate": "40.00"},
    ).json()

    response = client.patch(
        f"/api/requests/{card['id']}",
        json={
            "category": "FUEL",
            "details": {"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount"] == "150.00"
    assert len(body["lines"]) == 1
    assert "Бензин" in body["lines"][0]["title"]


def test_typed_request_lands_in_the_history_with_a_name(
    client, login, employee, manager, project, session
):
    """История работает и у категорийных заявок: имя, роль, «было → стало»."""
    login(employee)
    card = _create(
        client,
        employee,
        project,
        "MEALS",
        details={"meal_type": "Обед", "people": 4, "days": 2, "rate": "50.00"},
        submit=True,
    ).json()

    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})

    request = svc.get_request(session, card["id"], full=True)
    approved = [e for e in request.events if e.kind.value == "approved"][0]
    assert approved.employee_id == manager.id
    assert approved.actor_role == manager.role.value
    assert approved.details["amount_total"].startswith("400")


# --- подсказки не смешиваются --------------------------------------------


def test_typed_requests_do_not_pollute_material_hints(
    client, login, employee, project, session
):
    """Питание и карго не попадают в подсказки к полю «что нужно».

    «Обед и ужин» и «Карго, Оборудование Hikvision, Китай → Душанбе» —
    выведенные строки, а не материалы: никто не закажет их повторно с
    автодополнения, а ленту частого они забьют намертво.
    """
    from app.services import ai_memory

    login(employee)
    _create(
        client,
        employee,
        project,
        "MEALS",
        details={"meal_type": "Обед и ужин", "people": 4, "days": 2, "rate": "50.00"},
        submit=True,
    )
    _create(
        client,
        employee,
        project,
        "MATERIALS",
        lines=[{"title": "Кабель UTP Cat6", "quantity": 2, "unit": "бухта"}],
        submit=True,
    )

    titles = [item.title for item in ai_memory.frequent(session)]
    assert "Кабель UTP Cat6" in titles
    assert "Обед и ужин" not in titles


def test_material_catalog_skips_typed_requests(
    client, login, employee, project, session
):
    from app.services import ai_memory

    login(employee)
    _create(
        client,
        employee,
        project,
        "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
        submit=True,
    )
    catalog = [item.title for item in ai_memory.frequent(session, limit=50)]
    assert not any("Opel" in title for title in catalog)
