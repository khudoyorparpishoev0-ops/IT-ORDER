"""Планировщик: расписание, защита от повторов, напоминания и сводка."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.core.time import utcnow
from app.db.models import Employee, JobRun, MonthlyBudget, RequestStatus
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import jobs as jobs_svc
from app.services import reminders
from app.services import requests as svc
from app.services.schedule import STALE_REQUESTS, WEEKLY_BUDGET, due_jobs

TZ = ZoneInfo("Asia/Dushanbe")


def local(text: str) -> datetime:
    """Местное время из «2026-09-08 09:01»."""
    return datetime.fromisoformat(text).replace(tzinfo=TZ)


def _request(session, employee, project, *, days_ago: int, status=RequestStatus.PENDING):
    """Заявка, которая лежит на своём шаге нужное число дней."""
    request = svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Гипсокартон", quantity=Decimal("10"), unit="лист")],
        ),
    )
    long_ago = utcnow() - timedelta(days=days_ago)
    request.status = status
    request.submitted_at = long_ago
    request.sourcing_started_at = long_ago
    request.sourced_at = long_ago
    request.decided_at = long_ago
    request.created_at = long_ago
    session.flush()
    return request


# --- Расписание ------------------------------------------------------------


def test_job_fires_once_a_day_after_the_hour():
    before = due_jobs(local("2026-09-08 08:59"), reminder_hour=9, catch_up_hours=6)
    after = due_jobs(local("2026-09-08 09:01"), reminder_hour=9, catch_up_hours=6)

    assert f"{STALE_REQUESTS}:2026-09-08" not in [d.run_key for d in before]
    fresh = [d for d in after if d.run_key == f"{STALE_REQUESTS}:2026-09-08"]
    assert fresh and fresh[0].expired is False


def test_weekly_job_only_on_monday():
    monday = [d.job.name for d in due_jobs(local("2026-09-07 09:30"), reminder_hour=9, catch_up_hours=6)]
    tuesday = [
        d.job.name
        for d in due_jobs(local("2026-09-08 09:30"), reminder_hour=9, catch_up_hours=6)
        if not d.expired
    ]
    assert WEEKLY_BUDGET in monday
    assert WEEKLY_BUDGET not in tuesday


def test_late_start_catches_up_but_not_at_night():
    """Сервер поднялся через час — напоминание ещё нужно, через полсуток — нет."""
    hour_late = due_jobs(local("2026-09-08 10:00"), reminder_hour=9, catch_up_hours=6)
    at_night = due_jobs(local("2026-09-08 23:30"), reminder_hour=9, catch_up_hours=6)

    today = f"{STALE_REQUESTS}:2026-09-08"
    assert [d.expired for d in hour_late if d.run_key == today] == [False]
    assert [d.expired for d in at_night if d.run_key == today] == [True]


# --- Защита от повторов ----------------------------------------------------


def test_job_runs_once_even_if_tick_repeats(
    session, employee, manager, project, telegram_box
):
    _request(session, employee, project, days_ago=5)
    manager.telegram_chat_id = 700
    session.flush()

    moment = utcnow().replace(hour=6)  # 11:00 в Душанбе
    first = jobs_svc.run_due_jobs(session, now=moment)
    sent_after_first = len(telegram_box)
    second = jobs_svc.run_due_jobs(session, now=moment)

    assert first, "первый проход должен был отработать"
    assert second == [], "второй проход не должен слать ничего повторно"
    assert len(telegram_box) == sent_after_first


def test_missed_day_is_closed_without_sending(
    session, employee, manager, project, telegram_box
):
    """Сервер лежал до ночи: день закрываем, людей не будим."""
    _request(session, employee, project, days_ago=5)
    manager.telegram_chat_id = 700
    session.flush()

    # 23:30 по Душанбе — окно наверстывания давно прошло.
    jobs_svc.run_due_jobs(session, now=utcnow().replace(hour=18, minute=30))

    assert telegram_box == []
    statuses = {r.job: r.status for r in session.query(JobRun).all()}
    assert statuses[STALE_REQUESTS] == "SKIPPED"


def test_failed_job_is_recorded_and_does_not_raise(session, monkeypatch):
    def explode(session, *, now=None):
        raise RuntimeError("почта отвалилась")

    monkeypatch.setitem(jobs_svc.HANDLERS, STALE_REQUESTS, explode)
    jobs_svc.run_due_jobs(session, now=utcnow().replace(hour=6))

    # За вчера задача помечена пропущенной, за сегодня — упавшей.
    run = session.query(JobRun).filter_by(job=STALE_REQUESTS, status="FAILED").one()
    assert "почта отвалилась" in run.details


# --- Напоминания -----------------------------------------------------------


def test_reminder_goes_to_the_one_who_holds_the_request(
    session, employee, manager, procurement, project, advance, telegram_box, mailbox
):
    """Напоминание — тому, у кого заявка стоит, а не автору."""
    request = _request(session, employee, project, days_ago=4)
    manager.telegram_chat_id = 700
    employee.telegram_chat_id = 100
    session.flush()

    reminders.send_stale_reminders(session)

    assert [m.chat_id for m in telegram_box] == [700]
    assert request.number in telegram_box[0].text
    assert [letter["To"] for letter in mailbox] == [manager.email]


def test_fresh_request_is_not_a_reminder(
    session, employee, manager, project, telegram_box
):
    _request(session, employee, project, days_ago=1)
    manager.telegram_chat_id = 700
    session.flush()

    reminders.send_stale_reminders(session)
    assert telegram_box == []


def test_own_request_does_not_remind_its_author(
    session, manager, project, telegram_box
):
    """Руководитель подал заявку сам — согласовать её он всё равно не может."""
    _request(session, manager, project, days_ago=5)
    manager.telegram_chat_id = 700
    session.flush()

    reminders.send_stale_reminders(session)
    assert telegram_box == []


def test_one_letter_lists_all_stale_requests(
    session, employee, manager, project, mailbox
):
    first = _request(session, employee, project, days_ago=4)
    second = _request(session, employee, project, days_ago=6)
    session.flush()

    reminders.send_stale_reminders(session)

    assert len(mailbox) == 1, "на человека — одно письмо, а не письмо на заявку"
    body = mailbox[0].get_body(preferencelist=("plain",)).get_content()
    assert first.number in body and second.number in body


def test_reminder_respects_the_switch(session, employee, manager, project, telegram_box):
    _request(session, employee, project, days_ago=5)
    manager.telegram_chat_id = 700
    manager.notify_stale_requests = False
    session.flush()

    reminders.send_stale_reminders(session)
    assert telegram_box == []


def test_draft_reminds_its_author(session, employee, project, telegram_box):
    """Черновик держит сам автор — напоминаем ему."""
    _request(session, employee, project, days_ago=5, status=RequestStatus.DRAFT)
    employee.telegram_chat_id = 100
    session.flush()

    reminders.send_stale_reminders(session)
    assert [m.chat_id for m in telegram_box] == [100]


def test_paid_request_reminds_nobody(session, employee, manager, project, telegram_box):
    _request(session, employee, project, days_ago=9, status=RequestStatus.PAID)
    manager.telegram_chat_id = 700
    session.flush()

    reminders.send_stale_reminders(session)
    assert telegram_box == []


# --- Недельная сводка ------------------------------------------------------


def test_weekly_summary_counts_last_week(session, employee, manager, project, telegram_box):
    request = _request(session, employee, project, days_ago=8, status=RequestStatus.PAID)
    request.paid_at = utcnow() - timedelta(days=8)
    request.amount = Decimal("1500.00")
    manager.telegram_chat_id = 700
    manager.notify_weekly_budget = True
    session.add(
        MonthlyBudget(
            year=utcnow().year, month=utcnow().month, amount=Decimal("50000.00")
        )
    )
    session.flush()

    summary = reminders.week_summary(session)
    assert summary.paid_count == 1
    assert summary.paid_amount == Decimal("1500.00")
    assert summary.budget_limit == Decimal("50000.00")

    reminders.send_weekly_summary(session)
    assert [m.chat_id for m in telegram_box] == [700]
    assert "Бюджет месяца" in telegram_box[0].text


def test_weekly_summary_only_for_those_who_asked(
    session, employee, manager, project, telegram_box
):
    """По умолчанию сводка выключена: рассылать её всем подряд незачем."""
    manager.telegram_chat_id = 700
    employee.telegram_chat_id = 100
    employee.notify_weekly_budget = True  # права на отчёты у сотрудника нет
    session.flush()

    reminders.send_weekly_summary(session)
    assert telegram_box == []


# --- Ручной запуск из панели ----------------------------------------------


def test_admin_can_run_a_job_now(client, login, admin, employee, manager, project, session, telegram_box):
    _request(session, employee, project, days_ago=5)
    manager.telegram_chat_id = 700
    session.flush()

    login(admin)
    response = client.post(f"/api/jobs/{STALE_REQUESTS}/run")
    assert response.status_code == 200, response.text
    assert "получател" in response.json()["details"]
    assert len(telegram_box) == 1

    # Ручной запуск виден в журнале задач наравне с плановым.
    runs = client.get("/api/jobs")
    assert runs.status_code == 200
    manual = [r for r in runs.json() if r["details"] and "вручную" in r["details"]]
    assert manual and manual[0]["status"] == "DONE"


def test_jobs_are_closed_to_others(client, login, manager):
    login(manager)
    assert client.get("/api/jobs").status_code == 403
    assert client.post(f"/api/jobs/{STALE_REQUESTS}/run").status_code == 403


def test_unknown_job_is_rejected(client, login, admin):
    login(admin)
    assert client.post("/api/jobs/выдуманная/run").status_code == 422
