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
from app.schemas.ai import (
    AiBudgetOut,
    AiEmployeeCostOut,
    AiEntry,
    AiFeedbackIn,
    AiFeedbackSummaryOut,
    AiModelOut,
    AiPeriodOut,
    AiSettingsOut,
    AiUsage,
    AiUsageOut,
    AiUsageTypeOut,
)
from app.schemas.analytics import DeliveryStatsOut
from app.services import ai_feedback, ai_log, ai_memory, ai_usage
from app.services.notifications import intelligence as intel_notify

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
    usage = ai_log.stats(session) | ai_feedback.summary(session)
    return AiSettingsOut(
        enabled=settings.assistant_enabled,
        model=settings.assistant_model,
        key_mask=_mask(settings.anthropic_api_key),
        timeout_seconds=settings.assistant_timeout_seconds,
        prompt_overridden=bool(settings.assistant_prompt_file),
        analytics_prompt_overridden=bool(settings.analytics_prompt_file),
        usage=AiUsage(**usage),
        deliveries=DeliveryStatsOut(**intel_notify.stats(session)),
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


@router.get("/feedback/reasons", response_model=dict[str, str])
def feedback_reasons(_: CurrentUser):
    """Причины отрицательной оценки. Список закрытый: свободный текст в
    статистике не группируется, а «Другое» с комментарием закрывает
    остальные случаи."""
    return ai_feedback.REASONS


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def rate(session: DbSession, user: CurrentUser, data: AiFeedbackIn) -> Response:
    """Оценка ответа помощника. Оценить можно только своё обращение."""
    ai_feedback.rate(
        session,
        user,
        interaction_id=data.interaction_id,
        useful=data.useful,
        reason=data.reason,
        comment=data.comment,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/usage",
    response_model=AiUsageOut,
    dependencies=[Depends(RequirePermission(Permission.MANAGE_REFERENCE))],
)
def usage(session: DbSession, _: CurrentUser):
    """Расход на AI и польза от него: раздел администратора.

    Закрыт тем же правом, что справочники и карточка помощника: расход по
    сотрудникам — это данные обо всей компании, и рядовому сотруднику их
    видеть незачем. Считает всё сервер, панель показывает готовое.

    От доступности Anthropic раздел не зависит вовсе: он читает журнал
    обращений, а не спрашивает модель.
    """
    data = ai_usage.collect(session)
    return AiUsageOut(
        periods=[AiPeriodOut(**vars(p)) for p in data.periods],
        models=[AiModelOut(**vars(m)) for m in data.models],
        usage_types=[AiUsageTypeOut(**vars(u)) for u in data.usage_types],
        employees=[AiEmployeeCostOut(**vars(e)) for e in data.employees],
        feedback=AiFeedbackSummaryOut(**data.feedback),
        budget=AiBudgetOut(**vars(data.budget)),
        apply_rate_pct=data.apply_rate_pct,
        applied=data.applied,
        offered=data.offered,
        prices_checked=data.prices_checked,
    )
