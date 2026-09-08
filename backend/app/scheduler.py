"""Тикер фоновых задач: раз в минуту спрашивает, что пора запустить.

Живёт в процессе API — отдельный контейнер ради двух задач в сутки был бы
лишней деталью, которую нужно поднимать, обновлять и чинить. Повторов не
будет и при нескольких процессах: день занимается уникальным ключом в
базе (`app/services/jobs.py`).
"""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.db.session import get_session_factory
from app.services.jobs import run_due_jobs

log = logging.getLogger(__name__)


def _tick() -> None:
    """Один проход в собственной сессии. Синхронный: SQLAlchemy тут обычная."""
    session = get_session_factory()()
    try:
        run_due_jobs(session)
    finally:
        session.close()


async def scheduler_loop() -> None:
    """Цикл до остановки приложения."""
    settings = get_settings()
    log.info(
        "Планировщик запущен: напоминания в %02d:00 по %s",
        settings.reminder_hour,
        settings.app_timezone,
    )
    while True:
        try:
            # База синхронная, поэтому проход уходит в поток: иначе он
            # блокировал бы обработку запросов на всё время рассылки.
            await asyncio.to_thread(_tick)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            # Цикл не должен умирать: база могла быть недоступна минуту.
            log.exception("Проход планировщика не удался")
        await asyncio.sleep(settings.scheduler_tick_seconds)
