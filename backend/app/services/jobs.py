"""Запуск фоновых задач с защитой от повторов.

Расписание считает `app/services/schedule.py`, здесь — работа с базой:
занять день под задачу, выполнить, записать итог. Два процесса или
перезапуск контейнера не разошлют одно и то же дважды: `run_key`
уникален, и запуск получает тот, чья вставка прошла.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.time import to_local, utcnow
from app.db.models import JobRun
from app.services import reminders
from app.services.schedule import STALE_REQUESTS, WEEKLY_BUDGET, due_jobs

log = logging.getLogger(__name__)

#: Что делает каждая задача. Функция получает сессию и момент запуска,
#: возвращает строку для журнала задач.
HANDLERS = {
    STALE_REQUESTS: reminders.send_stale_reminders,
    WEEKLY_BUDGET: reminders.send_weekly_summary,
}

#: Понятные названия для панели и логов.
JOB_LABEL = {
    STALE_REQUESTS: "Напоминания о залежавшихся заявках",
    WEEKLY_BUDGET: "Недельная сводка по бюджету",
}


def _claim(session: Session, job: str, run_key: str) -> JobRun | None:
    """Занимает день под задачу. None — занял кто-то другой.

    Вставка с ON CONFLICT DO NOTHING атомарна, поэтому гонка двух
    процессов решается базой, а не порядком запуска.
    """
    session.execute(
        insert(JobRun)
        .values(job=job, run_key=run_key, status="RUNNING")
        .on_conflict_do_nothing(index_elements=[JobRun.run_key])
    )
    session.commit()

    run = session.scalar(select(JobRun).where(JobRun.run_key == run_key))
    if run is None or run.status != "RUNNING":
        return None
    return run


def _finish(session: Session, run: JobRun, status: str, details: str | None) -> None:
    run.status = status
    run.details = details[:500] if details else None
    run.finished_at = utcnow()
    session.commit()


def run_due_jobs(session: Session, *, now: datetime | None = None) -> list[str]:
    """Выполняет всё, чему пришло время. Возвращает описания запусков."""
    settings = get_settings()
    moment = now or utcnow()
    done: list[str] = []

    for due in due_jobs(
        to_local(moment),
        reminder_hour=settings.reminder_hour,
        catch_up_hours=settings.scheduler_catch_up_hours,
    ):
        run = _claim(session, due.job.name, due.run_key)
        if run is None:
            continue

        if due.expired:
            # Окно наверстывания закрыто: день закрываем, но не шумим.
            _finish(session, run, "SKIPPED", "Пропущено: время запуска прошло")
            log.info("Задача %s пропущена: %s", due.job.name, due.run_key)
            continue

        try:
            details = HANDLERS[due.job.name](session, now=moment)
        except Exception as exc:  # noqa: BLE001
            # Упавшая задача не должна ронять цикл: завтра будет новый
            # день и новый запуск, а причина останется в журнале.
            session.rollback()
            _finish(session, run, "FAILED", f"{type(exc).__name__}: {exc}")
            log.exception("Задача %s не выполнена", due.job.name)
            continue

        _finish(session, run, "DONE", details)
        done.append(f"{due.run_key}: {details}")
        log.info("Задача %s выполнена: %s", due.job.name, details)

    return done


def run_now(session: Session, job: str, *, now: datetime | None = None) -> str:
    """Ручной запуск задачи из панели.

    Расписание и защиту от повторов обходит намеренно: администратор
    нажимает кнопку, чтобы проверить настройку почты и бота, а не чтобы
    дождаться девяти утра. В журнале запусков такой прогон виден наравне
    с обычными — по нему и понятно, что рассылка дошла.
    """
    if job not in HANDLERS:
        from app.core.errors import ValidationError

        raise ValidationError(f"Неизвестная задача: {job}")

    moment = now or utcnow()
    # Ключ с меткой времени: ручных запусков за день может быть несколько,
    # и каждый должен остаться в журнале отдельной строкой.
    run_key = f"{job}:manual:{moment.isoformat(timespec='seconds')}"
    run = _claim(session, job, run_key)

    try:
        details = HANDLERS[job](session, now=moment)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if run is not None:
            _finish(session, run, "FAILED", f"{type(exc).__name__}: {exc}")
        raise

    if run is not None:
        _finish(session, run, "DONE", f"вручную · {details}")
    return details
