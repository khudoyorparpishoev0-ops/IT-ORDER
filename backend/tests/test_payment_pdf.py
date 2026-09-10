"""Заявка на оплату — внутренний документ IT-HONA LLC.

Проверяется не «PDF собрался», а то, ради чего он существует: бухгалтер
открывает файл и без объяснений понимает, кто просил, что оплачиваем,
сколько, как посчитано и кто согласовал. И то, чего в документе быть не
должно ни при каких данных.
"""

from __future__ import annotations

import re

import pytest

from app.db.models import ExpenseRequest
from app.services import export_pdf

PDF_MAGIC = b"%PDF-"


def _text(content: bytes) -> str:
    """Текст всех страниц. Читаем готовый файл, а не свои же черновики:
    проверять надо то, что увидит человек."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(content)
    return "\n".join(page.get_textpage().get_text_range() for page in doc)


def _pages(content: bytes) -> int:
    import pypdfium2 as pdfium

    return len(pdfium.PdfDocument(content))


def _make(client, employee, project, category, details=None, lines=None, submit=True):
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
    response = client.post("/api/requests", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _pdf(client, request_id: int) -> bytes:
    response = client.get(f"/api/exports/requests/{request_id}.pdf")
    assert response.status_code == 200, response.text
    assert response.content.startswith(PDF_MAGIC)
    return response.content


pytest.importorskip("pypdfium2", reason="нечем прочитать готовый PDF")


# --- документ как документ ------------------------------------------------


def test_document_calls_itself_a_payment_request(
    client, login, employee, manager, project
):
    """Название одно и то же на всех заявках: это не накладная и не акт."""
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    text = _text(_pdf(client, card["id"]))
    assert "ЗАЯВКА НА ОПЛАТУ" in text
    assert card["number"] in text
    assert "IT-HONA LLC" in text
    for wrong in ("накладная", "счёт-фактура", "акт выполненных"):
        assert wrong.lower() not in text.lower()


def test_product_is_named_order_not_hona_order(client, login, employee, project):
    """Продукт называется ORDER. «HONA ORDER» в документе не встречается."""
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    text = _text(_pdf(client, card["id"]))
    assert "ORDER" in text
    assert "HONA ORDER" not in text


def test_footer_repeats_number_and_pages(client, login, employee, project):
    """Подвал на каждой странице: листы расшивают, и лист без номера
    теряет принадлежность."""
    login(employee)
    lines = [
        {"title": f"Позиция {i}: кабель силовой ВВГнг-LS 3×2,5 мм² в бухтах", "quantity": i, "unit": "бухта"}
        for i in range(1, 33)
    ]
    card = _make(client, employee, project, "MATERIALS", lines=lines)
    content = _pdf(client, card["id"])
    pages = _pages(content)
    assert pages >= 2, "тридцать две позиции на один лист не помещаются"

    text = _text(content)
    assert text.count("ВНУТРЕННИЙ ДОКУМЕНТ") == pages
    assert f"Стр. {pages} / {pages}" in text
    assert text.count(card["number"]) >= pages


def test_long_names_do_not_run_off_the_page(client, login, employee, project):
    """Длинное наименование переносится, а не уезжает за поле."""
    long_title = (
        "Кабель управления с медными многопроволочными жилами КВВГЭнг(А)-LS "
        "10×1,5 мм², экранированный, в бухтах по 200 метров, поставка партиями"
    )
    login(employee)
    card = _make(
        client, employee, project, "MATERIALS",
        lines=[{"title": long_title, "quantity": 3, "unit": "бухта"}],
    )
    text = _text(_pdf(client, card["id"]))
    # Текст переносится, поэтому ищем начало и конец по отдельности.
    assert "Кабель управления" in text
    assert "поставка партиями" in text


def test_table_header_repeats_on_every_page(client, login, employee, project):
    login(employee)
    lines = [
        {"title": f"Позиция {i}", "quantity": 1, "unit": "шт."} for i in range(1, 60)
    ]
    card = _make(client, employee, project, "MATERIALS", lines=lines)
    content = _pdf(client, card["id"])
    text = _text(content)
    assert text.count("НАИМЕНОВАНИЕ") == _pages(content)


# --- документ зависит от вида расхода -------------------------------------


def test_meals_show_people_and_days_not_pieces(client, login, employee, project):
    """«Обед · 2 шт.» бухгалтеру ничего не объясняет, «2 чел. × 1 день» —
    объясняет полностью."""
    login(employee)
    card = _make(
        client, employee, project, "MEALS",
        details={"meal_type": "Обед", "people": 2, "days": 1, "rate": "20.00"},
    )
    text = _text(_pdf(client, card["id"]))
    assert "ДЕТАЛИ РАСХОДА" in text
    assert "Количество человек" in text
    assert "РАСЧЁТ" in text
    assert "2 чел." in text and "1 день" in text
    assert "40,00 TJS" in text
    assert "шт." not in text


def test_trip_shows_route_dates_and_articles(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "TRIP",
        details={
            "staff": "Парпишоев Худоёр Абдулхаевич",
            "destination": "Душанбе → Регар",
            "purpose": "Монтаж оборудования",
            "date_from": "2026-09-11",
            "date_to": "2026-09-13",
            "transport": "300.00",
            "lodging": "600.00",
            "per_diem": "300.00",
            "other": "100.00",
        },
    )
    text = _text(_pdf(client, card["id"]))
    assert "КОМАНДИРОВКА" in text
    # Стрелки нет ни в одном шрифте проекта — в документе она дефис.
    assert "Душанбе — Регар" in text
    assert "11.09.2026 — 13.09.2026" in text
    assert "Количество дней" in text
    assert "Суточные" in text
    assert "1 300,00 TJS" in text


def test_cargo_shows_weight_volume_and_customs(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "CARGO",
        details={
            "from_country": "Китай",
            "from_city": "Shenzhen",
            "to_city": "Душанбе",
            "what": "Оборудование Hikvision",
            "places": 5,
            "weight_kg": 120,
            "cargo_cost": "1500.00",
            "customs": "400.00",
            "extra": "100.00",
        },
    )
    text = _text(_pdf(client, card["id"]))
    assert "КАРГО И ЛОГИСТИКА" in text
    assert "Китай, Shenzhen" in text
    assert "120 кг" in text
    assert "Таможенные расходы" in text
    assert "2 000,00 TJS" in text


def test_delivery_shows_route(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "DELIVERY",
        details={
            "from_place": "Ориён-Медиа",
            "to_place": "Асри Нав",
            "what": "Жёсткий диск",
            "amount": "30.00",
        },
    )
    text = _text(_pdf(client, card["id"]))
    assert "ДОСТАВКА" in text
    assert "Ориён-Медиа" in text and "Асри Нав" in text
    assert "30,00 TJS" in text


def test_fuel_shows_vehicle_and_litres(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={
            "vehicle": "Opel",
            "plate": "01 AB 234 KT",
            "kind": "Бензин",
            "liters": 20,
            "amount": "150.00",
        },
    )
    text = _text(_pdf(client, card["id"]))
    assert "ТРАНСПОРТНЫЙ РАСХОД" in text
    assert "01 AB 234 KT" in text
    assert "20 л" in text


def test_service_shows_contractor(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "SERVICES",
        details={
            "service": "Чистка офиса",
            "description": "Влажная уборка, два часа",
            "contractor": "ЧП «Тоза»",
            "amount": "72.00",
        },
    )
    text = _text(_pdf(client, card["id"]))
    assert "УСЛУГА" in text
    assert "Чистка офиса" in text
    assert "ЧП «Тоза»" in text


def test_connectivity_shows_service_and_period(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "CONNECTIVITY",
        details={
            "service_kind": "Хостинг",
            "account": "sofo-hotel.tj",
            "period": "1 год",
            "amount": "271.00",
        },
    )
    text = _text(_pdf(client, card["id"]))
    assert "sofo-hotel.tj" in text
    assert "1 год" in text
    assert "271,00 TJS" in text


def test_materials_keep_the_estimate_table(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "MATERIALS",
        lines=[
            {"title": "Кабель UTP Cat6, внутренний, медь", "quantity": 2, "unit": "бухта"},
            {"title": "Коннектор RJ45 Cat6", "quantity": 100, "unit": "шт."},
        ],
    )
    text = _text(_pdf(client, card["id"]))
    assert "НАИМЕНОВАНИЕ" in text
    assert "Коннектор RJ45 Cat6" in text
    assert "бухта" in text


# --- итог, статус и согласование ------------------------------------------


def test_total_is_present_and_named(client, login, employee, project):
    """Сумму ищут первой: она отдельным блоком, а не строкой таблицы."""
    login(employee)
    card = _make(
        client, employee, project, "MEALS",
        details={"meal_type": "Обед", "people": 3, "days": 4, "rate": "25.50"},
    )
    text = _text(_pdf(client, card["id"]))
    assert "ИТОГО К ОПЛАТЕ" in text
    # 3 × 4 × 25,50 — копейки не теряются.
    assert "306,00 TJS" in text


def test_unpriced_request_says_so_instead_of_zero(
    client, login, employee, project
):
    """Ноль в графе суммы читается как «бесплатно». Пишем словами."""
    login(employee)
    card = _make(
        client, employee, project, "MATERIALS",
        lines=[{"title": "Цемент М500", "quantity": 40, "unit": "мешок"}],
    )
    text = _text(_pdf(client, card["id"]))
    assert "не определена" in text
    assert "ИТОГО К ОПЛАТЕ" not in text


def test_status_is_shown_and_follows_the_request(
    client, login, employee, manager, finance, project
):
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    assert "СОГЛАСОВАНИЕ ПОКУПКИ" in _text(_pdf(client, card["id"]))

    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})
    assert "К ОПЛАТЕ" in _text(_pdf(client, card["id"]))

    login(finance)
    client.post(
        f"/api/requests/{card['id']}/payment",
        json={"method": "cash", "document": "РКО-7"},
    )
    text = _text(_pdf(client, card["id"]))
    assert "ОПЛАЧЕНА" in text
    assert "РКО-7" in text


def test_approval_names_people_and_roles(
    client, login, employee, manager, finance, project
):
    """Главный вопрос документа: кто согласовал и кто заплатил."""
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    login(manager)
    client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": True, "comment": "Согласовано"},
    )
    login(finance)
    client.post(
        f"/api/requests/{card['id']}/payment",
        json={"method": "cash", "document": "РКО-8"},
    )

    text = _text(_pdf(client, card["id"]))
    assert "СОГЛАСОВАНИЕ" in text
    assert employee.full_name in text
    assert manager.full_name in text
    assert finance.full_name in text
    assert "Руководитель" in text and "Бухгалтерия" in text
    assert "ОПЛАТА" in text


def test_system_steps_are_signed_by_order_not_by_a_person(
    client, login, employee, manager, project
):
    """Маршрут выбрала система. Приписывать его человеку значит
    утверждать, что он сделал два действия вместо одного."""
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})

    text = _text(_pdf(client, card["id"]))
    assert "Системное действие" in text
    assert "ПЕРЕДАЧА В БУХГАЛТЕРИЮ" in text


def test_comments_have_author_role_and_time(
    client, login, employee, manager, project
):
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    login(manager)
    client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": True, "comment": "Цена согласована с поставщиком."},
    )
    text = _text(_pdf(client, card["id"]))
    assert "КОММЕНТАРИИ" in text
    assert "Цена согласована с поставщиком." in text
    assert manager.full_name in text


def test_no_comments_no_section(client, login, employee, project):
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    assert "КОММЕНТАРИИ" not in _text(_pdf(client, card["id"]))


def test_rejected_request_exports(client, login, employee, manager, project):
    login(employee)
    card = _make(
        client, employee, project, "MEALS",
        details={"meal_type": "Ужин", "people": 12, "days": 5, "rate": "90.00"},
    )
    login(manager)
    client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": False, "comment": "Превышение бюджета объекта."},
    )
    text = _text(_pdf(client, card["id"]))
    assert "ОТКЛОНЕНА" in text
    assert "ОТКЛОНЕНИЕ ЗАЯВКИ" in text
    assert "Превышение бюджета объекта." in text


# --- чего в документе быть не должно --------------------------------------


def test_document_leaks_no_secrets(
    client, login, employee, manager, finance, project
):
    """Ни адресов, ни токенов, ни кодов. Проверка тупая намеренно:
    документ распечатывают и кладут в папку."""
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    login(manager)
    client.post(f"/api/requests/{card['id']}/decision", json={"approve": True})
    login(finance)
    client.post(
        f"/api/requests/{card['id']}/payment",
        json={"method": "cash", "document": "РКО-9"},
    )

    text = _text(_pdf(client, card["id"])).lower()
    for word in (
        "password", "пароль", "token", "jwt", "secret", "session",
        "totp", "recovery", "api key", "traceback", "127.0.0.1",
    ):
        assert word not in text
    # Адреса в ORDER не собираются вовсе, но убедимся, что их нет и здесь.
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text)


def test_qr_holds_a_plain_request_url(client, login, employee, project, monkeypatch):
    """В коде обычный адрес заявки. Ни токена, ни одноразовой ссылки:
    открывший его увидит заявку, только если имеет на неё право."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "public_base_url", "https://order.ithona.tj")
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    code = export_pdf.QrCode(f"https://order.ithona.tj/requests/{card['id']}")
    assert code.url == f"https://order.ithona.tj/requests/{card['id']}"
    assert "token" not in code.url and "jwt" not in code.url
    # Матрица строится — значит код читаемый, а не пустой квадрат.
    assert len(code._build()) > 20

    content = _pdf(client, card["id"])
    assert content.startswith(PDF_MAGIC)


def test_without_public_url_there_is_no_qr(client, login, employee, project, monkeypatch):
    """Без адреса вести некуда: код с «/requests/28» внутри телефон
    никуда не приведёт, поэтому его просто нет."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "public_base_url", "")
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    text = _text(_pdf(client, card["id"]))
    assert "Открыть" not in text


# --- данные из заявки, а не из запроса ------------------------------------


def test_markup_in_a_title_does_not_break_the_export(
    client, login, employee, project
):
    """«Уголок <30мм» роняло выгрузку: `Paragraph` разбирает мини-XML.
    А «Кабель <b>» подделывал вёрстку документа."""
    login(employee)
    card = _make(
        client, employee, project, "MATERIALS",
        lines=[
            {"title": "Уголок <30мм & труба", "quantity": 2, "unit": "шт."},
            {"title": "Кабель <b>жирный</b>", "quantity": 1, "unit": "м"},
        ],
    )
    text = _text(_pdf(client, card["id"]))
    assert "Уголок <30мм & труба" in text
    assert "Кабель <b>жирный</b>" in text


def test_arrow_survives_as_a_dash(client, login, employee, project):
    """Стрелки нет ни в одном шрифте проекта, и reportlab её не рисует
    вовсе: «Душанбе → Регар» печаталось как «Душанбе Регар»."""
    login(employee)
    card = _make(
        client, employee, project, "DELIVERY",
        details={
            "from_place": "Ориён-Медиа",
            "to_place": "Асри Нав",
            "what": "Груз → срочно",
            "amount": "30.00",
        },
    )
    text = _text(_pdf(client, card["id"]))
    assert "Груз — срочно" in text


def test_client_cannot_forge_the_approver(
    client, login, employee, manager, project
):
    """Имя согласовавшего берётся из журнала заявки, а не из запроса."""
    login(employee)
    card = _make(
        client, employee, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    login(manager)
    client.post(
        f"/api/requests/{card['id']}/decision",
        json={"approve": True, "actor": "Кто-то Другой"},
    )
    text = _text(_pdf(client, card["id"]))
    assert manager.full_name in text
    assert "Кто-то Другой" not in text


def test_legacy_request_without_category_still_exports(
    client, login, employee, project, session
):
    """Заявки, поданные до категорийных форм, продолжают выгружаться."""
    login(employee)
    card = _make(
        client, employee, project, "MATERIALS",
        lines=[{"title": "Цемент М500", "quantity": 40, "unit": "мешок"}],
        submit=False,
    )
    row = session.get(ExpenseRequest, card["id"])
    row.category = None
    row.details = {}
    session.flush()

    text = _text(_pdf(client, card["id"]))
    assert "не указана" in text
    assert "Цемент М500" in text
    assert "ЗАЯВКА НА ОПЛАТУ" in text


def test_foreign_request_is_not_exported(client, login, employee, manager, project):
    login(manager)
    card = _make(
        client, manager, project, "FUEL",
        details={"vehicle": "Opel", "kind": "Бензин", "amount": "150.00"},
    )
    login(employee)
    assert client.get(f"/api/exports/requests/{card['id']}.pdf").status_code == 404
