"""Проверка здоровья.

Отвечает 200 даже при сломанной базе: по полям `database` и `migrations`
видно, что именно не так. Различать эти два случая важно — «база не
поднялась» и «база жива, но миграции не применены» чинятся по-разному.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.core.time import utcnow
from app.db.session import get_engine

log = logging.getLogger(__name__)
router = APIRouter(tags=["service"])


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    database = "ok"
    migrations = "unknown"
    revision: str | None = None

    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
            try:
                revision = conn.scalar(text("select version_num from alembic_version"))
                migrations = "applied" if revision else "empty"
            except SQLAlchemyError:
                # Таблицы alembic_version нет: база поднята, но не размечена.
                migrations = "not_applied"
    except SQLAlchemyError as exc:
        database = "unavailable"
        migrations = "unknown"
        log.warning("Health: база недоступна: %s", type(exc).__name__)

    return {
        "status": "ok" if database == "ok" else "degraded",
        "app": settings.app_name,
        "timezone": settings.app_timezone,
        "database": database,
        "migrations": migrations,
        "db_revision": revision,
        "time": utcnow().isoformat(),
    }
