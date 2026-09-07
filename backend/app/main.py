"""Точка входа FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.router import api_router
from app.config import get_settings
from app.core.logging import setup_logging

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
    yield
    log.info("%s остановлен", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.2.0",
        summary="Заявки сотрудников на расходы: подача, согласование, выплата",
        lifespan=lifespan,
        # CORS не нужен: панель отдаётся тем же origin через nginx.
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
