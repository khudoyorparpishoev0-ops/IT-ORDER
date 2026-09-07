"""Сборка всех роутеров."""

from fastapi import APIRouter

from app.api.routes import auth, exports, health, reference, reports, requests

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(reference.router)
api_router.include_router(requests.router)
api_router.include_router(reports.router)
api_router.include_router(exports.router)
