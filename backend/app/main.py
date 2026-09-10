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
        "%s запускается: пояс %s", settings.app_name, settings.app_timezone
    )
    # Состояние каналов — в лог при старте. Иначе «почему не приходит?»
    # разбирается вслепую: по логам не видно даже, дошёл ли токен до
    # контейнера, а переменные окружения в логи писать нельзя.
    log.info(
        "Почта: %s. Telegram: %s. Push на телефон: %s",
        "настроена" if settings.mail_enabled else "не настроена (SMTP_*)",
        (
            f"бот @{settings.telegram_bot_username}"
            if settings.telegram_enabled and settings.telegram_bot_username
            else "токен есть, но не задано TELEGRAM_BOT_USERNAME"
            if settings.telegram_enabled
            else "не настроен (TELEGRAM_BOT_TOKEN)"
        ),
        "настроен" if settings.push_enabled else "не настроен (VAPID_PRIVATE_KEY)",
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

    # Напоминания и недельная сводка. Отдельный контейнер ради двух задач
    # в сутки не нужен: повторов не будет и при нескольких процессах —
    # день занимается уникальным ключом в базе.
    task = None
    if settings.scheduler_enabled:
        import asyncio

        from app.scheduler import scheduler_loop

        task = asyncio.create_task(scheduler_loop())
    else:
        log.info("Планировщик выключен (SCHEDULER_ENABLED=false)")

    yield

    if task is not None:
        task.cancel()
    log.info("%s остановлен", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.3.0",
        summary="Заявки сотрудников на расходы: подача, согласование, выплата",
        lifespan=lifespan,
        # CORS не нужен: панель отдаётся тем же origin через nginx.
        #
        # Документация открыта только в разработке. На боевом сервере она
        # отдавала бы любому прохожему полную карту API: все эндпоинты,
        # все параметры, все схемы. Данных это не раскрывает — каждый
        # эндпоинт закрыт правом, — но избавляет нападающего от разведки,
        # а нас лишает возможности заметить её по логам.
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.is_development else None,
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
