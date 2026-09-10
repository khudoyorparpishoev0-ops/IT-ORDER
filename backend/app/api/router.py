"""Сборка всех роутеров."""

from fastapi import APIRouter

from app.api.routes import (
    ai,
    analytics,
    assistant,
    audit,
    auth,
    exports,
    health,
    jobs,
    reference,
    push,
    reports,
    requests,
    telegram,
    templates,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(reference.router)
api_router.include_router(assistant.router)
api_router.include_router(analytics.router)
api_router.include_router(ai.router)
api_router.include_router(requests.router)
api_router.include_router(templates.router)
api_router.include_router(reports.router)
api_router.include_router(exports.router)
api_router.include_router(audit.router)
api_router.include_router(jobs.router)
api_router.include_router(telegram.router)
api_router.include_router(push.router)
