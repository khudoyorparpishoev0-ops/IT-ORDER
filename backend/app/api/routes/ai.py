"""Служебный раздел помощника: отметка «пригодилось» и состояние для админа.

Ключ Anthropic здесь не появляется даже частично сверх маски: он живёт в
ENV на сервере, в панель не отдаётся и в журнал обращений не пишется.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, DbSession, RequirePermission, bind_audit_actor
from app.config import get_settings
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.core.time import to_local
from app.db.models import AiKind
from app.schemas.ai import AiEntry, AiSettingsOut, AiUsage
from app.services import ai_log, ai_memory

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(bind_audit_actor)])


@router.post(
    "/applied/{interaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def mark_applied(session: DbSession, user: CurrentUser, interaction_id: int) -> Response:
    """Человек воспользовался ответом помощника.

    Открыто любому вошедшему, но отмечать можно только своё обращение:
    чужое не находится вовсе — как чужая заявка, чтобы перебором номеров
    нельзя было выяснить, сколько раз спрашивали коллеги.
    """
    entry = ai_log.mark_applied(session, interaction_id, employee_id=user.id)
    if entry is None:
        raise NotFoundError("Обращение не найдено")

    # Принятая поправка написания становится общим знанием: следующему
    # сотруднику она придёт мгновенно и без обращения к модели. Заполняет
    # эту таблицу только согласие человека — руками её никто не ведёт.
    if entry.kind is AiKind.MATERIAL and entry.question and entry.answer:
        ai_memory.remember_alias(
            session, wrote=entry.question, canonical=entry.answer, unit=None
        )
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/settings",
    response_model=AiSettingsOut,
    dependencies=[Depends(RequirePermission(Permission.MANAGE_REFERENCE))],
)
def settings_(session: DbSession, _: CurrentUser):
    """Что администратор должен видеть, не заходя на сервер: работает ли
    помощник, какой моделью, сколько им пользуются и что отвечает."""
    settings = get_settings()
    usage = ai_log.stats(session)
    return AiSettingsOut(
        enabled=settings.assistant_enabled,
        model=settings.assistant_model,
        key_mask=_mask(settings.anthropic_api_key),
        timeout_seconds=settings.assistant_timeout_seconds,
        prompt_overridden=bool(settings.assistant_prompt_file),
        analytics_prompt_overridden=bool(settings.analytics_prompt_file),
        usage=AiUsage(**usage),
        recent=[
            AiEntry(
                id=entry.id,
                kind=entry.kind.value,
                source=entry.source.value,
                username=entry.username,
                question=entry.question,
                answer=entry.answer,
                ok=entry.ok,
                error=entry.error,
                applied=entry.applied,
                duration_ms=entry.duration_ms,
                created_at=to_local(entry.created_at).isoformat(),
            )
            for entry in ai_log.recent(session)
        ],
    )


def _mask(key: str | None) -> str | None:
    """Ключ узнаваем, но бесполезен: начало и четыре последних знака.

    Начало у всех ключей Anthropic одинаковое, а четырёх знаков хватает,
    чтобы отличить действующий ключ от старого, который забыли заменить.
    """
    key = (key or "").strip()
    if not key:
        return None
    if len(key) <= 12:
        return "…" + key[-4:]
    return f"{key[:11]}…{key[-4:]}"
