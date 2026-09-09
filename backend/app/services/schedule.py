"""Расписание фоновых задач — чистые функции, без базы и без сети.

Полноценный планировщик (APScheduler, celery-beat) здесь был бы лишним:
задач две, обе раз в сутки. Вместо этого приложение раз в минуту
спрашивает у этого модуля, что уже пора запустить, а защиту от повторов
даёт уникальный ключ запуска в базе.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

#: Задача напоминаний о залежавшихся заявках.
STALE_REQUESTS = "stale_requests"
#: Недельная сводка по бюджету.
WEEKLY_BUDGET = "weekly_budget"
#: Чистка журнала обращений к AI по сроку хранения.
AI_RETENTION = "ai_retention"


@dataclass(frozen=True)
class Job:
    """Задача и её расписание в местном времени.

    `weekday` — день недели по `date.weekday()` (0 — понедельник);
    None означает «каждый день».
    """

    name: str
    hour: int
    weekday: int | None = None

    def scheduled_for(self, moment: datetime) -> datetime:
        """Момент запуска в те сутки, в которые попадает `moment`."""
        return moment.replace(hour=self.hour, minute=0, second=0, microsecond=0)

    def run_key(self, moment: datetime) -> str:
        """Ключ запуска: задача и местная дата. Уникален в базе."""
        return f"{self.name}:{moment.date().isoformat()}"


def jobs(*, reminder_hour: int) -> list[Job]:
    """Список задач. Час общий: людям проще, когда всё приходит разом."""
    return [
        Job(STALE_REQUESTS, hour=reminder_hour),
        # Понедельник: сводка нужна в начале недели, а не в её конце.
        Job(WEEKLY_BUDGET, hour=reminder_hour, weekday=0),
        # Чистка идёт ночью: она ничего никому не шлёт, а днём лишний
        # DELETE по большой таблице ни к чему.
        Job(AI_RETENTION, hour=3),
    ]


@dataclass(frozen=True)
class Due:
    """Задача, время которой пришло."""

    job: Job
    run_key: str
    #: Назначенный момент уже прошёл, но окно наверстывания закрыто:
    #: запускать поздно, а день закрыть нужно, иначе задача выстрелит
    #: посреди ночи при следующем запуске сервера.
    expired: bool


def due_jobs(
    now_local: datetime, *, reminder_hour: int, catch_up_hours: int
) -> list[Due]:
    """Что пора запустить в этот момент.

    Смотрим и на сегодня, и на вчера: сервер мог быть выключен в момент
    запуска задачи, и напоминание, опоздавшее на час, всё ещё полезно.
    Более старые дни не разбираем — просроченное напоминание о позавчера
    ничего не меняет.
    """
    result: list[Due] = []
    for job in jobs(reminder_hour=reminder_hour):
        for day_shift in (0, 1):
            moment = now_local - timedelta(days=day_shift)
            if job.weekday is not None and moment.weekday() != job.weekday:
                continue
            planned = job.scheduled_for(moment)
            if planned > now_local:
                continue
            expired = now_local - planned > timedelta(hours=catch_up_hours)
            result.append(Due(job=job, run_key=job.run_key(moment), expired=expired))
    return result
