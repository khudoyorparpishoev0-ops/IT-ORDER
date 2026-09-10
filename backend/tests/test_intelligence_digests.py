"""Автоматические сводки ORDER Intelligence: кому, когда и сколько раз.

Здесь проверяется не содержание сводки (оно живёт в
`test_analytics_service.py`), а поведение рассылки: пора ли, положено
ли, дошло ли и не пришло ли дважды. Всё, что может разбудить человека
ночью или прийти к нему трижды подряд, должно быть закрыто тестом —
исправлять такое на боевом сервере поздно, доверие к рассылке теряется
с первого раза.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.time import utcnow
from app.db.models import (
    EmployeeRole,
    ExpenseRequest,
    IntelligenceDelivery,
    IntelligenceKind,
)
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import jobs
from app.services import requests as svc
from app.services.notifications import dedup, intelligence as notify

DUSHANBE = ZoneInfo("Asia/Dushanbe")


def subscribe(session, employee, **kwargs):
    """Включает рассылку. Значения по умолчанию — как у нового человека."""
    employee.intelligence_enabled = True
    employee.telegram_chat_id = kwargs.pop("chat_id", 900)
    for key, value in kwargs.items():
        setattr(employee, key, value)
    session.commit()
    return employee


def at(hour: int, minute: int = 0, *, day: int = 15) -> datetime:
    """Момент в поясе Душанбе, приведённый к UTC: сравнивать удобнее так."""
    return datetime(2026, 9, day, hour, minute, tzinfo=DUSHANBE)


def stuck(session, employee, project, *, hours: int = 40, title: str = "Цемент М500"):
    """Заявка, которая давно стоит: без неё сводке не о чем говорить."""
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title=title, quantity=1, unit="шт.")],
            submit=True,
        ),
    )
    session.commit()
    row = session.get(ExpenseRequest, request.id)
    moment = utcnow() - timedelta(hours=hours)
    row.created_at = moment
    row.submitted_at = moment
    session.commit()
    return row


def deliveries(session, kind: IntelligenceKind | None = None):
    stmt = select(IntelligenceDelivery)
    if kind is not None:
        stmt = stmt.where(IntelligenceDelivery.kind == kind)
    return list(session.scalars(stmt))


# --- Время получателя ------------------------------------------------------------------


def test_corporate_timezone_is_the_fallback(session, manager) -> None:
    """Пояс не задан — считаем по корпоративному Asia/Dushanbe."""
    subscribe(session, manager, timezone=None)
    assert notify.timezone_of(manager).key == "Asia/Dushanbe"


def test_unknown_timezone_does_not_stop_the_digest(session, manager) -> None:
    """Опечатка в поясе не должна оставлять человека без сводки."""
    subscribe(session, manager, timezone="Марс/Олимп")
    assert notify.timezone_of(manager).key == "Asia/Dushanbe"


def test_morning_goes_by_local_time(session, manager) -> None:
    """У каждого своё утро: девять в Душанбе — не девять в Москве."""
    subscribe(session, manager, timezone="Europe/Moscow", digest_morning_time=time(9, 0))

    # 09:00 в Душанбе — это 06:00 в Москве: ещё рано.
    assert notify.due_now(manager, IntelligenceKind.MORNING, at(9)) is False
    # 12:00 в Душанбе — 09:00 в Москве: пора.
    assert notify.due_now(manager, IntelligenceKind.MORNING, at(12)) is True


def test_evening_has_its_own_time(session, manager) -> None:
    subscribe(session, manager, digest_evening_time=time(18, 0))
    assert notify.due_now(manager, IntelligenceKind.EVENING, at(17, 30)) is False
    assert notify.due_now(manager, IntelligenceKind.EVENING, at(18, 1)) is True


def test_disabled_digest_never_comes_due(session, manager) -> None:
    subscribe(session, manager, digest_morning_enabled=False)
    assert notify.due_now(manager, IntelligenceKind.MORNING, at(23)) is False


# --- Кому можно ------------------------------------------------------------------------


def test_employee_without_reports_gets_nothing(
    session, employee, project, telegram_box
) -> None:
    """Право проверяется в момент отправки, а не при подписке."""
    stuck(session, employee, project)
    subscribe(session, employee)

    result = notify.send_digests(session, IntelligenceKind.MORNING, now=at(10))

    assert telegram_box == []
    assert "отправлено 0" in result


def test_permission_lost_after_subscribing(
    session, manager, employee, project, telegram_box
) -> None:
    """Роль понизили — старая настройка правом доступа не становится."""
    stuck(session, employee, project)
    subscribe(session, manager)
    manager.role = EmployeeRole.EMPLOYEE
    session.commit()

    notify.send_digests(session, IntelligenceKind.MORNING, now=at(10))

    assert telegram_box == []


def test_disabled_employee_is_skipped_but_keeps_the_setting(
    session, manager, employee, project, telegram_box
) -> None:
    stuck(session, employee, project)
    subscribe(session, manager)
    manager.active = False
    session.commit()

    notify.send_digests(session, IntelligenceKind.MORNING, now=at(10))

    assert telegram_box == []
    # Настройка остаётся: вернут на работу — рассылка продолжится.
    assert manager.intelligence_enabled is True


def test_without_telegram_nothing_is_delivered(
    session, manager, employee, project, telegram_box
) -> None:
    stuck(session, employee, project)
    subscribe(session, manager, chat_id=None)

    notify.send_digests(session, IntelligenceKind.MORNING, now=at(10))

    assert telegram_box == []
    assert manager.intelligence_enabled is True


# --- Сборка и отправка ------------------------------------------------------------------


def test_morning_digest_is_sent_once_a_day(
    session, manager, employee, project, telegram_box
) -> None:
    stuck(session, employee, project)
    subscribe(session, manager)

    notify.send_digests(session, IntelligenceKind.MORNING, now=at(9, 5))
    notify.send_digests(session, IntelligenceKind.MORNING, now=at(9, 25))
    notify.send_digests(session, IntelligenceKind.MORNING, now=at(11))

    assert len(telegram_box) == 1
    assert "Утро" in telegram_box[0].text
    rows = deliveries(session, IntelligenceKind.MORNING)
    assert len(rows) == 1 and rows[0].sent_count == 1


def test_next_day_brings_a_new_digest(
    session, manager, employee, project, telegram_box
) -> None:
    """Ключ включает местную дату: назавтра сводка приходит снова."""
    stuck(session, employee, project)
    subscribe(session, manager)

    notify.send_digests(session, IntelligenceKind.MORNING, now=at(9, 5, day=15))
    notify.send_digests(session, IntelligenceKind.MORNING, now=at(9, 5, day=16))

    assert len(telegram_box) == 2


def test_digest_works_without_the_model(
    session, manager, employee, project, telegram_box
) -> None:
    """Молчание Claude не отменяет сводку: цифры считает сервер.

    Транспорт помощника в тестах по умолчанию выключен, поэтому этот тест
    и проверяет именно запасной путь.
    """
    stuck(session, employee, project)
    subscribe(session, manager)

    notify.send_digests(session, IntelligenceKind.MORNING, now=at(10))

    assert len(telegram_box) == 1
    text = telegram_box[0].text
    assert "Активные:" in text and "Требуют внимания:" in text
    assert deliveries(session, IntelligenceKind.MORNING)[0].ai_used is False


def test_empty_evening_is_not_sent(session, manager, telegram_box) -> None:
    """Пустая сводка — это спам. По умолчанию её нет."""
    subscribe(session, manager, digest_when_no_changes=False)

    result = notify.send_digests(session, IntelligenceKind.EVENING, now=at(18, 5))

    assert telegram_box == []
    assert "пропущено 1" in result
    row = deliveries(session, IntelligenceKind.EVENING)[0]
    assert row.delivered_at is None


def test_empty_evening_is_sent_when_asked(session, manager, telegram_box) -> None:
    """Кто просил короткую строку — получает её, а не пустоту."""
    subscribe(session, manager, digest_when_no_changes=True)

    notify.send_digests(session, IntelligenceKind.EVENING, now=at(18, 5))

    assert len(telegram_box) == 1
    assert telegram_box[0].text == "ORDER: критических изменений за день нет."


def test_one_broken_recipient_does_not_stop_the_rest(
    session, manager, finance, employee, project, telegram_box, monkeypatch
) -> None:
    """Сбой доставки одному не отменяет остальных и не роняет задачу."""
    stuck(session, employee, project)
    subscribe(session, manager)
    subscribe(session, finance, chat_id=901)

    from app.core import telegram as tg

    class Broken:
        def send(self, message):
            if message.chat_id == 900:
                raise tg.TelegramError("bot was blocked by the user")
            telegram_box.append(message)

    tg.set_transport(Broken())
    result = notify.send_digests(session, IntelligenceKind.MORNING, now=at(10))
    tg.set_transport(None)

    assert len(telegram_box) == 1 and telegram_box[0].chat_id == 901
    assert "ошибок 1" in result
    failed = [r for r in deliveries(session, IntelligenceKind.MORNING) if not r.ok]
    assert len(failed) == 1 and "blocked" in failed[0].error


# --- Срочные сигналы --------------------------------------------------------------------


def test_critical_alert_is_sent_and_not_repeated_too_soon(
    session, manager, employee, project, telegram_box
) -> None:
    """Повтор — не чаще, чем раз в CRITICAL_ALERT_REPEAT_HOURS."""
    stuck(session, employee, project, hours=40)
    subscribe(session, manager)

    first = utcnow()
    notify.scan_critical(session, now=first)
    assert len(telegram_box) == 1

    notify.scan_critical(session, now=first + timedelta(hours=1))
    notify.scan_critical(session, now=first + timedelta(hours=6))
    assert len(telegram_box) == 1

    notify.scan_critical(session, now=first + timedelta(hours=13))
    assert len(telegram_box) == 2
    assert "Напоминание" in telegram_box[1].text


def test_ordinary_delay_is_not_an_alert(
    session, manager, employee, project, telegram_box
) -> None:
    """Сигнал — про критичное, обычная просрочка ждёт утренней сводки."""
    # Норматив согласования — 8 часов; критичным считается двукратное
    # превышение, поэтому десять часов сигналом не становятся.
    stuck(session, employee, project, hours=10)
    subscribe(session, manager)

    result = notify.scan_critical(session, now=utcnow())

    assert telegram_box == []
    assert result.startswith("новых 0")


def test_resolved_problem_closes_quietly(
    session, manager, employee, project, procurement, telegram_box
) -> None:
    """«Починилось» отдельным сообщением не приходит — только числом."""
    request = stuck(session, employee, project, hours=40)
    subscribe(session, manager)

    moment = utcnow()
    notify.scan_critical(session, now=moment)
    assert len(telegram_box) == 1

    # Заявку сдвинули с места: на согласовании она больше не стоит.
    from app.schemas.request import DecisionIn

    svc.decide_request(session, request.id, DecisionIn(approve=True, actor=manager.full_name))
    session.commit()

    closed = notify.scan_critical(session, now=moment + timedelta(minutes=30))

    assert len(telegram_box) == 1, "о снятой проблеме отдельно не пишем"
    assert "закрыто 1" in closed
    assert dedup.resolved_today(session, manager, now=moment + timedelta(minutes=30)) == 1


def test_alerts_can_be_switched_off(
    session, manager, employee, project, telegram_box
) -> None:
    stuck(session, employee, project, hours=40)
    subscribe(session, manager, critical_alerts_enabled=False)

    notify.scan_critical(session, now=utcnow())

    assert telegram_box == []


# --- Планировщик ------------------------------------------------------------------------


def test_scheduler_does_not_duplicate_after_restart(
    session, manager, employee, project, telegram_box
) -> None:
    """Тикер зовут каждую минуту и после перезапуска — сводка одна.

    Защита та же, что у остальных фоновых задач: уникальный ключ и
    вставка, которую разрешает база, а не порядок запуска процессов.
    """
    stuck(session, employee, project)
    subscribe(session, manager)

    moment = at(9, 30)
    for _ in range(5):
        jobs.run_intelligence(session, now=moment)
        moment += timedelta(minutes=1)

    assert len([m for m in telegram_box if "Утро" in m.text]) == 1


def test_critical_scan_happens_once_per_window(
    session, manager, employee, project, telegram_box
) -> None:
    """Сканирование идёт по окнам, а не на каждом тике."""
    stuck(session, employee, project, hours=40)
    subscribe(session, manager, digest_morning_enabled=False, digest_evening_enabled=False)

    moment = at(9, 30)
    jobs.run_intelligence(session, now=moment)
    jobs.run_intelligence(session, now=moment + timedelta(minutes=1))

    assert len(telegram_box) == 1


def test_jobs_are_registered(session) -> None:
    """Задачи живут в общем планировщике, второго планировщика нет."""
    from app.services.schedule import INTELLIGENCE_CRITICAL, INTELLIGENCE_DIGESTS

    assert INTELLIGENCE_DIGESTS in jobs.HANDLERS
    assert INTELLIGENCE_CRITICAL in jobs.HANDLERS
    assert INTELLIGENCE_DIGESTS in jobs.JOB_LABEL


def test_manual_run_sends_the_digest(
    session, manager, employee, project, telegram_box
) -> None:
    """Ручной прогон из «Параметров» проверяет настройку целиком."""
    stuck(session, employee, project)
    subscribe(session, manager)

    from app.services.schedule import INTELLIGENCE_DIGESTS

    details = jobs.run_now(session, INTELLIGENCE_DIGESTS, now=at(10))

    assert "утро" in details
    assert len(telegram_box) == 1


# --- Настройки -------------------------------------------------------------------------


def test_settings_round_trip(client, session, login, manager) -> None:
    login(manager)

    before = client.get("/api/analytics/subscription")
    assert before.status_code == 200
    assert before.json()["enabled"] is False
    assert before.json()["timezone_hint"] == "Asia/Dushanbe"

    saved = client.patch(
        "/api/analytics/subscription",
        json={"enabled": True, "morning_time": "07:30", "timezone": "Europe/Moscow"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["enabled"] is True
    assert body["morning_time"] == "07:30"
    assert body["timezone"] == "Europe/Moscow"


def test_unknown_timezone_is_rejected(client, session, login, manager) -> None:
    """Ошибку показываем сразу, а не молча подставляем корпоративный пояс."""
    login(manager)
    answer = client.patch(
        "/api/analytics/subscription", json={"timezone": "Марс/Олимп"}
    )
    assert answer.status_code == 422


def test_settings_are_closed_to_employees(client, session, login, employee) -> None:
    login(employee)
    assert client.get("/api/analytics/subscription").status_code == 403


@pytest.mark.parametrize("field", ["morning_sent", "critical_sent", "failed"])
def test_admin_sees_delivery_metrics(
    client, session, login, admin, manager, employee, project, telegram_box, field
) -> None:
    stuck(session, employee, project)
    subscribe(session, manager)
    notify.send_digests(session, IntelligenceKind.MORNING, now=at(10))

    login(admin)
    body = client.get("/api/ai/settings").json()

    assert field in body["deliveries"]
    assert body["deliveries"]["morning_sent"] == 1
    assert body["deliveries"]["subscribers"] == 1


def test_frequent_scan_does_not_hide_daily_jobs(
    client, session, login, admin, manager, employee, project, telegram_box
) -> None:
    """Сканирование идёт каждые двадцать минут и не должно вытеснять из
    списка ежедневные рассылки: смотрят сюда как раз затем, чтобы
    проверить, ушли ли они."""
    stuck(session, employee, project, hours=40)
    subscribe(session, manager)

    from app.services.schedule import INTELLIGENCE_CRITICAL, STALE_REQUESTS

    jobs.run_now(session, STALE_REQUESTS, now=at(9))
    moment = at(9, 30)
    for _ in range(12):
        jobs.run_intelligence(session, now=moment)
        moment += timedelta(minutes=30)

    login(admin)
    rows = client.get("/api/jobs").json()
    names = [row["job"] for row in rows]

    assert STALE_REQUESTS in names
    assert names.count(INTELLIGENCE_CRITICAL) <= 5
