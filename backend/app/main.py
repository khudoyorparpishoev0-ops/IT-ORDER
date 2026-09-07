"""Точка входа FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.errors import register_error_handlers
from app.api.router import api_router
from app.config import get_settings
from app.core.audit_context import set_ip
from app.core.logging import setup_logging
from app.db.session import get_session_factory
from app.services.auth import ensure_bootstrap_admin

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info(
        "%s запускается: пояс %s, порог автоодобрения %s",
        settings.app_name,
        settings.app_timezone,
        settings.auto_approve_threshold,
    )

    # Свежую систему некому настроить: войти нельзя, а завести пользователя
    # может только вошедший. Стартовый администратор разрывает этот круг.
    try:
        session = get_session_factory()()
        try:
            ensure_bootstrap_admin(session)
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        # База может быть ещё не поднята — приложение должно стартовать
        # и отвечать на /health, а не падать в цикл перезапусков.
        log.warning("Стартовый администратор не создан: %s", type(exc).__name__)

    yield
    log.info("%s остановлен", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.3.0",
        summary="Заявки сотрудников на расходы: подача, согласование, выплата",
        lifespan=lifespan,
        # CORS не нужен: панель отдаётся тем же origin через nginx.
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    register_error_handlers(app)

    @app.middleware("http")
    async def remember_client_ip(request: Request, call_next):
        """Кладёт адрес клиента в контекст запроса — для журнала.

        Панель отдаётся через nginx и Caddy, поэтому в request.client
        всегда адрес прокси. Настоящий берём из первого звена
        X-Forwarded-For: его выставляет наш же прокси. Заголовок можно
        подделать, но за нашим прокси он перезаписывается, а сам по себе
        адрес — справка для разбора, не пропуск.
        """
        forwarded = request.headers.get("x-forwarded-for", "")
        client = forwarded.split(",")[0].strip() if forwarded else None
        set_ip(client or (request.client.host if request.client else None))
        return await call_next(request)

    app.include_router(api_router)
    return app


app = create_app()
