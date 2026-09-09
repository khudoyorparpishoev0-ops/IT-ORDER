"""Аналитика для руководителя. Только чтение и объяснение.

Раздел закрыт правом `view_reports` целиком: сводка по компании — не
дело рядового сотрудника и не дело отдела закупа. Модель получает
готовые цифры и не может обойти это ограничение вопросом, потому что
данных, которых человеку не положено видеть, в её блоке фактов нет.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, RequirePermission, bind_audit_actor
from app.core.permissions import Permission
from app.schemas.analytics import AnalyticsAskIn, AnalyticsReplyOut, DigestOut
from app.services import analytics, intelligence
from app.services.audit import write_audit

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[
        Depends(bind_audit_actor),
        Depends(RequirePermission(Permission.VIEW_REPORTS)),
    ],
)


@router.get("/digest", response_model=DigestOut)
def digest(
    session: DbSession,
    _: CurrentUser,
    ai: bool = Query(
        default=True,
        description="false — только цифры, без обращения к модели и без платы за него",
    ),
):
    """Сводка: счётчики, заявки на внимание, этапы, объекты, тренды.

    Цифры считает сервер, поэтому сводка работает и без AI: без ключа
    просто не будет объясняющего текста. Карточке на дашборде текст не
    нужен — она зовёт этот же эндпоинт с `ai=false`, чтобы каждый заход
    на дашборд не стоил денег.
    """
    if not ai:
        return analytics.digest_facts(session)
    return intelligence.digest(session)


@router.post("/ask", response_model=AnalyticsReplyOut)
def ask(session: DbSession, user: CurrentUser, data: AnalyticsAskIn):
    """Вопрос руководителя обычными словами.

    Пишем в журнал, кто и о чём спрашивал: аналитика показывает данные по
    всей компании, и след обращения должен остаться, как у любого другого
    доступа к чужим заявкам.
    """
    write_audit(
        session,
        entity="analytics",
        entity_id="ask",
        action="ai_question",
        details=data.question.strip()[:500],
    )
    session.commit()
    return intelligence.ask(session, question=data.question, history=data.history)
