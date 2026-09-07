"""Перевод ошибок домена в HTTP-ответы."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.services.auth import AuthError

log = logging.getLogger(__name__)

_STATUS = {
    AuthError: 401,
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
}


def register_error_handlers(app: FastAPI) -> None:
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        status = _STATUS[type(exc)]
        if status >= 500:
            log.exception("Ошибка домена на %s", request.url.path)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    for error_type in _STATUS:
        app.add_exception_handler(error_type, handle)
