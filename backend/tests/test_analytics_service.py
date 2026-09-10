"""ORDER Intelligence: расчёты сервера, права и разрешённые намерения.

Главное, что здесь проверяется: все числа считает база, модель их не
трогает; аналитика закрыта правом; произвольного SQL у модели нет.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.time import utcnow
from app.db.models import (
    AiInteraction,
    AuditLog,
    ExpenseRequest,
    Project,
    RequestCategory,
    RequestStatus,
)
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import requests as svc
from app.services.analytics import (
    anomalies,
    attention,
    digest,
    executive,
    intents,
    scope,
    sla,
    stale,
)
from app.services.analytics import inconsistencies as inc


def submit(session, employee, project, *titles, unit="шт.", quantity=1, category=None):
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            category=category,
            lines=[
                ExpenseLineIn(title=t, quantity=quantity, unit=unit) for t in titles
            ],
            submit=True,
        ),
    )
    session.commit()
    return request


def age(session, request, hours: int) -> ExpenseRequest:
    """Состаривает заявку: ждать восемь часов в тесте нечем."""
    return age_at(session, request, utcnow(), hours=hours)


def age_at(session, request, now: datetime, *, hours: int) -> ExpenseRequest:
    """То же, но относительно заданного момента, а не текущего.

    Нужно там, где проверяется сравнение «утро → вечер»: оно считается от
    часа утренней сводки, и прогон в полночь видел бы одно, а в полдень —
    другое. Тест, который зелёный только в рабочие часы, не проверяет
    ничего — он сообщает время суток.
    """
    row = session.get(ExpenseRequest, request.id)
    moment = now - timedelta(hours=hours)
    row.created_at = moment
    row.submitted_at = moment
    session.commit()
    return row


def evening_of_today() -> datetime:
    """Местные 18:00 сегодняшнего дня — точка отсчёта для вечерней сводки.

    После утреннего часа при любых настройках, поэтому «сегодняшнее
    утро» для этого момента однозначно.
    """
    from app.core.time import to_local

    local = to_local(utcnow()).replace(hour=18, minute=0, second=0, microsecond=0)
    return local.astimezone(UTC)


# --- Нормативы -------------------------------------------------------------------


def test_sla_comes_from_one_place() -> None:
    """Нормативы не разбросаны по приложению: их спрашивают у sla."""
    norms = sla.norms()
    assert norms[RequestStatus.PENDING] == 8
    assert norms[RequestStatus.SOURCING] == 24
    # Черновик нормативом не ограничен: он у автора.
    assert norms[RequestStatus.DRAFT] is None


def test_sla_is_configurable(monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "sla_pending_hours", 2)
    assert sla.norms()[RequestStatus.PENDING] == 2


def test_stale_threshold_is_configurable(monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "stale_hours", 6)
    assert sla.stale_hours() == 6


# --- Заявки без движения ----------------------------------------------------------


def test_fresh_request_is_not_stuck(session, employee, project) -> None:
    submit(session, employee, project, "Цемент М500")
    assert stale.stuck_requests(session) == []


def test_overdue_by_norm(session, employee, project) -> None:
    request = submit(session, employee, project, "Цемент М500")
    age(session, request, hours=10)

    (found,) = stale.stuck_requests(session)
    assert found.number == request.number
    assert found.overdue is True
    assert found.severity == "warning"
    assert found.hours_in_status == 10
    assert found.norm_hours == 8
    assert "при нормативе 8 ч" in found.reason
    # Ответственный назван человеческим языком, а не кодом статуса.
    assert "руководител" in found.assignee.lower()


def test_double_the_norm_is_critical(session, employee, project) -> None:
    request = submit(session, employee, project, "Цемент М500")
    age(session, request, hours=20)
    assert stale.stuck_requests(session)[0].severity == "critical"


def test_hours_counted_from_the_current_step(session, employee, project, advance) -> None:
    """Время идёт от входа в текущий шаг, а не от подачи.

    Заявка, поданная неделю назад и только что пришедшая в закуп, стоит
    минуты, а не неделю, — и в очереди задержавшихся ей не место.
    """
    request = submit(session, employee, project, "Цемент М500")
    age(session, request, hours=200)
    assert stale.stuck_requests(session), "до перехода она давно просрочена"

    advance(request, to="sourcing")
    session.commit()

    row = session.get(ExpenseRequest, request.id)
    assert stale.hours_in_status(row, utcnow()) < 2
    assert stale.stuck_requests(session) == [], "у закупа она только что"


# --- Нестыковки -------------------------------------------------------------------


@pytest.mark.parametrize(
    "title, quantity, flagged",
    [
        ("2 мешка цемента", 5, True),
        ("два мешка цемента", 2, False),
        ("Шпатель 45 см", 1, False),
        ("Цемент М500", 20, False),
        ("Кабель ВВГ 3×2,5", 2, False),
    ],
)
def test_quantity_mismatch_is_narrow(session, employee, project, title, quantity, flagged) -> None:
    """Правило намеренно узкое: «45 см» — размер, «М500» — марка.

    Предупреждение, которое чаще неверно, чем верно, учит игнорировать
    все предупреждения подряд.
    """
    submit(session, employee, project, title, quantity=quantity)
    codes = [i.code for i in inc.find_all(session)]
    assert ("quantity_mismatch" in codes) is flagged


def test_missing_unit_is_only_info(session, employee, project) -> None:
    submit(session, employee, project, "Цемент М500", unit="")
    found = [i for i in inc.find_all(session) if i.code == "no_unit"]
    assert found and found[0].severity == "info"


def test_missing_category_is_noticed(session, employee, project) -> None:
    submit(session, employee, project, "Цемент М500")
    assert "no_category" in [i.code for i in inc.find_all(session)]


def test_category_set_is_not_flagged(session, employee, project) -> None:
    submit(session, employee, project, "Бензин", category=RequestCategory.FUEL)
    assert "no_category" not in [i.code for i in inc.find_all(session)]


def test_issues_are_facts_not_blame(session, employee, project) -> None:
    submit(session, employee, project, "Цемент М500", unit="")
    for issue in inc.find_all(session):
        low = issue.detail.lower()
        for word in ("плохо", "виноват", "халатн", "не справляется"):
            assert word not in low


# --- Отклонения от обычного уровня --------------------------------------------------


def test_no_history_no_anomalies(session, employee, project) -> None:
    submit(session, employee, project, "Цемент М500")
    assert anomalies.find(session) == []


def test_growth_is_reported_without_accusation(session, employee, project) -> None:
    """Неделя против недели: всплеск заявок — факт, а не нарушение."""
    now = utcnow()
    for i in range(8):
        request = submit(session, employee, project, f"Материал {i}")
        session.get(ExpenseRequest, request.id).created_at = now - timedelta(days=2)
    for i in range(3):
        request = submit(session, employee, project, f"Старый материал {i}")
        session.get(ExpenseRequest, request.id).created_at = now - timedelta(days=9)
    session.commit()

    found = anomalies.find(session, now=now)
    assert found, "рост с 3 до 8 за неделю должен быть замечен"
    week = next(a for a in found if a.code == "requests_week")
    assert week.change_pct > 0
    assert "обычного уровня" in week.detail
    for a in found:
        assert "нарушен" not in a.detail.lower()


def test_small_numbers_are_not_anomalies(session, employee, project) -> None:
    """Рост с одной заявки до двух — это «плюс 100%» и ничего не значит."""
    now = utcnow()
    request = submit(session, employee, project, "Цемент")
    session.get(ExpenseRequest, request.id).created_at = now - timedelta(days=9)
    submit(session, employee, project, "Цемент")
    session.commit()
    assert [a for a in anomalies.find(session, now=now) if a.code == "requests_week"] == []


# --- Сводка руководителя --------------------------------------------------------------


def test_overview_counts_everything_server_side(session, employee, project) -> None:
    fresh = submit(session, employee, project, "Цемент М500")
    late = submit(session, employee, project, "Песок речной")
    age(session, late, hours=30)

    data = executive.overview(session)
    assert data.active_requests == 2
    assert data.overdue == 1
    assert data.requires_attention >= 1
    assert isinstance(data.amount_active, Decimal)
    assert [p.code for p in data.problems if p.code == "overdue"]
    # Подпись склоняется по числу: «1 просрочена», а не «1 просрочены».
    assert next(p.label for p in data.problems if p.code == "overdue") == "просрочена"
    del fresh


def test_attention_counts_a_request_once(session, employee, project) -> None:
    """Две причины у одной заявки — это одно дело, а не два."""
    request = submit(session, employee, project, "Цемент М500", unit="")
    age(session, request, hours=30)

    queue = attention.requires_attention(session)
    assert len(queue) == 1
    assert len(queue[0].reasons) >= 1
    assert executive.overview(session).requires_attention == 1


def test_attention_sorts_critical_first(session, employee, project) -> None:
    mild = submit(session, employee, project, "Песок")
    severe = submit(session, employee, project, "Цемент")
    age(session, mild, hours=10)
    age(session, severe, hours=40)

    queue = attention.requires_attention(session)
    assert queue[0].number == severe.number
    assert queue[0].severity == "critical"


# --- Права ------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/analytics/executive-overview", "/api/analytics/intelligence"])
def test_employee_has_no_executive_analytics(client, login, employee, path) -> None:
    login(employee)
    assert client.get(path).status_code == 403


def test_procurement_has_no_executive_analytics(client, login, procurement) -> None:
    login(procurement)
    assert client.get("/api/analytics/executive-overview").status_code == 403


@pytest.mark.parametrize("role_fixture", ["manager", "finance", "admin"])
def test_reports_right_opens_analytics(client, login, request, role_fixture) -> None:
    login(request.getfixturevalue(role_fixture))
    assert client.get("/api/analytics/executive-overview").status_code == 200


def test_anonymous_is_rejected(client) -> None:
    assert client.get("/api/analytics/executive-overview").status_code == 401


def test_scope_refuses_without_the_right(employee) -> None:
    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        scope.for_employee(employee)


def test_scope_of_a_manager_is_the_company(manager) -> None:
    """Закрепления за объектами в ORDER нет — и мы его не выдумываем."""
    result = scope.for_employee(manager)
    assert result.all_company is True
    assert result.allows_project(123) is True


# --- Разрешённые намерения ---------------------------------------------------------------


def test_every_intent_runs(session, employee, project) -> None:
    submit(session, employee, project, "Цемент М500")
    box = scope.Scope(employee_id=employee.id)
    for name in intents.names():
        assert intents.run(session, name, scope=box, now=utcnow()) is not None


def test_unknown_intent_falls_back(session, employee, project) -> None:
    """Модель пишет текст, а не код: выдуманное имя — не повод падать."""
    submit(session, employee, project, "Цемент М500")
    result = intents.run(
        session, "drop table requests", scope=scope.Scope(employee_id=1), now=utcnow()
    )
    assert isinstance(result, executive.Overview)


def test_catalog_lists_names_for_the_model() -> None:
    catalog = intents.catalog()
    for name in intents.names():
        assert name in catalog


def test_model_picks_intent_server_runs_it(
    client, login, manager, employee, project, session, assistant_box
) -> None:
    """Модель называет намерение, функцию выполняет сервер."""
    request = submit(session, employee, project, "Цемент М500")
    age(session, request, hours=30)

    assistant_box.by_schema = {"_Intent": {"intent": "overdue"}}
    assistant_box.answer = {
        "answer": "Одна заявка вышла за норматив.",
        "bullets": [],
        "requests": [{"number": request.number, "why": "стоит 30 часов"}],
        "recommendations": [],
    }

    login(manager)
    body = client.post("/api/analytics/ask", json={"question": "какие заявки зависли"}).json()

    assert body["available"] is True
    assert [r["number"] for r in body["requests"]] == [request.number]
    # Первый запрос — выбор намерения, и данных в нём нет.
    assert "overdue" in assistant_box.prompts[0]
    assert request.number not in assistant_box.prompts[0]
    # Второй — ответ по данным, которые достал сервер.
    assert "ДАННЫЕ (overdue)" in assistant_box.prompts[1]


def test_invented_number_is_dropped(
    client, login, manager, employee, project, session, assistant_box
) -> None:
    submit(session, employee, project, "Цемент М500")
    assistant_box.by_schema = {"_Intent": {"intent": "overview"}}
    assistant_box.answer = {
        "answer": "Проверьте заявку.",
        "bullets": [],
        "requests": [{"number": "РЗ-9999", "why": "выдумка"}],
        "recommendations": [],
    }

    login(manager)
    body = client.post("/api/analytics/ask", json={"question": "что зависло"}).json()
    assert body["requests"] == []


def test_analytics_access_leaves_a_trace(client, login, manager, session) -> None:
    """Данные всей компании — доступ должен оставлять след."""
    login(manager)
    client.get("/api/analytics/executive-overview")

    rows = session.scalars(select(AuditLog).where(AuditLog.entity == "analytics")).all()
    assert [r.action for r in rows] == ["analytics_view"]
    assert rows[0].username == manager.full_name
    assert "без AI" in rows[0].details


def test_numbers_work_without_the_model(client, login, manager, employee, project, session) -> None:
    """Ключа нет — цифры на месте, нет только объяснения."""
    from app.core import assistant

    assistant.set_transport(None)
    submit(session, employee, project, "Цемент М500")

    login(manager)
    body = client.get("/api/analytics/intelligence").json()
    assert body["ai"]["enabled"] is False
    assert body["overview"]["active_requests"] == 1
    assert body["blind_spots"]


def test_model_failure_keeps_the_numbers(
    client, login, manager, employee, project, session, assistant_box
) -> None:
    submit(session, employee, project, "Цемент М500")
    assistant_box.answer = None

    login(manager)
    body = client.get("/api/analytics/intelligence").json()
    assert body["ai"] == {
        "enabled": True,
        "available": False,
        "headline": None,
        "summary": [],
        "recommendations": [],
    }
    assert body["overview"]["active_requests"] == 1


def test_ai_call_is_recorded(
    client, login, manager, employee, project, session, assistant_box
) -> None:
    submit(session, employee, project, "Цемент М500")
    assistant_box.answer = {
        "headline": "Всё спокойно",
        "summary": [],
        "recommendations": [],
    }

    login(manager)
    client.get("/api/analytics/intelligence")

    (entry,) = session.scalars(select(AiInteraction)).all()
    assert entry.question == "Сводка руководителя"


# --- Сводки -------------------------------------------------------------------------------


def test_morning_digest_has_numbers(session, employee, project) -> None:
    request = submit(session, employee, project, "Цемент М500")
    age(session, request, hours=30)

    data = digest.morning(session)
    text = digest.as_text(data)
    assert data.kind == "morning"
    assert "Активные: 1" in text
    assert "Просрочено: 1" in text
    assert "Основные проблемы" in text
    assert request.number in text


def test_evening_digest_says_what_is_left(session, employee, project) -> None:
    request = submit(session, employee, project, "Цемент М500")
    age(session, request, hours=30)

    text = digest.as_text(digest.evening(session))
    assert "Осталось активных: 1" in text
    assert "На завтра: 1 заявка" in text


def test_empty_evening_digest_is_honest(session) -> None:
    assert "На завтра ничего не висит" in digest.as_text(digest.evening(session))


@pytest.mark.parametrize("kind", ["morning", "evening"])
def test_digest_endpoint_needs_the_right(client, login, employee, manager, kind) -> None:
    login(employee)
    assert client.get(f"/api/analytics/digest/{kind}").status_code == 403
    login(manager)
    assert client.get(f"/api/analytics/digest/{kind}").json()["kind"] == kind


# --- Категории -------------------------------------------------------------------------------


def test_category_is_optional(session, employee, project) -> None:
    """NULL честно значит «не указана», а не «Другое»."""
    request = submit(session, employee, project, "Цемент М500")
    assert session.get(ExpenseRequest, request.id).category is None


def test_category_is_stored(session, employee, project) -> None:
    request = submit(session, employee, project, "Бензин", category=RequestCategory.FUEL)
    assert session.get(ExpenseRequest, request.id).category is RequestCategory.FUEL


def test_category_survives_the_api(client, login, employee, project) -> None:
    login(employee)
    created = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "category": "TRANSPORT",
            "lines": [{"title": "Такси до объекта", "quantity": 1, "unit": "поездка"}],
            "submit": False,
        },
    )
    assert created.status_code == 201


# --- Сравнение «утро → вечер» ------------------------------------------------------


def test_evening_compares_against_a_recomputed_baseline(session, employee, project) -> None:
    """Модель утреннюю сводку не помнит — сервер пересчитывает её сам."""
    from app.services.analytics.digest import overdue_delta

    now = evening_of_today()
    # Просрочилась ещё вчера: к утру уже стояла.
    old = submit(session, employee, project, "Цемент М500")
    age_at(session, old, now, hours=40)
    # Просрочилась после утренней сводки: норматив 8 часов, стоит 9.
    fresh = submit(session, employee, project, "Песок речной")
    age_at(session, fresh, now, hours=9)

    delta = overdue_delta(session, now=now)
    assert delta["left"] == 1, "вчерашняя всё ещё стоит"
    assert delta["new"] == 1, "сегодняшняя просрочилась после утра"
    assert delta["resolved"] == 0


def test_resolved_counts_closed_morning_overdue(session, employee, project, advance) -> None:
    """Закрытая за день утренняя просрочка попадает в «устранено»."""
    from app.services.analytics.digest import overdue_delta

    now = evening_of_today()
    request = submit(session, employee, project, "Цемент М500")
    age_at(session, request, now, hours=40)
    # Проводим до оплаты: заявка закрыта сегодня.
    advance(request, to="approved")
    row = session.get(ExpenseRequest, request.id)
    row.decided_at = now - timedelta(hours=40)
    session.commit()

    from app.services import requests as rsvc
    from app.schemas.request import PaymentIn

    rsvc.pay_request(
        session, row.id, PaymentIn(method="cash", document="РКО-1", actor="Бухгалтер")
    )
    session.commit()

    assert overdue_delta(session, now=now)["resolved"] == 1


def test_fresh_request_is_in_no_bucket(session, employee, project) -> None:
    from app.services.analytics.digest import overdue_delta

    submit(session, employee, project, "Цемент М500")
    assert overdue_delta(session, now=utcnow()) == {"resolved": 0, "left": 0, "new": 0}


def test_evening_text_shows_the_delta(session, employee, project) -> None:
    request = submit(session, employee, project, "Цемент М500")
    age(session, request, hours=40)

    text = digest.as_text(digest.evening(session))
    assert "Из утренних просрочек" in text
    assert "устранено: 0" in text
    assert "осталось: 1" in text
