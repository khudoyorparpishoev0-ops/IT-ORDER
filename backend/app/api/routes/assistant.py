"""Помощник по заявке. Только советы: ничего не создаёт и не меняет."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, bind_audit_actor
from app.core.permissions import Permission, has_permission
from app.schemas.assistant import (
    AssistantAskIn,
    AssistantReplyOut,
    DuplicateCheckIn,
    DuplicateCheckOut,
    MemoryItem,
    MemoryOut,
    SimilarRequestOut,
)
from app.services import ai_memory, request_assistant

# Открыт любому вошедшему: помощь нужна тому, кто заполняет заявку.
# Ключ Claude живёт только здесь, на сервере, и наружу не отдаётся.
router = APIRouter(
    prefix="/api/assistant",
    tags=["assistant"],
    dependencies=[Depends(bind_audit_actor)],
)


@router.post("/request", response_model=AssistantReplyOut)
def ask(session: DbSession, user: CurrentUser, data: AssistantAskIn):
    """Реплика диалога с помощником.

    Имя сотрудника берётся из сессии, а не из тела запроса: подставлять
    в контекст чужое имя незачем.
    """
    # Имя и id сотрудника ставит сервер: подсказки из личной истории
    # должны быть историей того, кто спрашивает, а не того, кого назвали
    # в теле запроса.
    context = data.context.model_copy(
        update={"employee_name": user.full_name, "employee_id": user.id}
    )
    return request_assistant.converse(
        session, text=data.text, history=data.history, context=context
    )


@router.get("/memory", response_model=MemoryOut)
def memory(
    session: DbSession,
    user: CurrentUser,
    project_id: int | None = Query(default=None),
):
    """Что ORDER помнит о заявках: частое, своё и по объекту.

    Модель здесь не участвует вовсе — это запросы к базе. Поэтому
    подсказки работают и при выключенном помощнике: кончился баланс у
    Anthropic, а автодополнение осталось на месте.
    """
    return MemoryOut(
        frequent=[_item(x) for x in ai_memory.frequent(session, project_id=project_id)],
        mine=[_item(x) for x in ai_memory.mine(session, user.id)],
        project=(
            [_item(x) for x in ai_memory.by_project(session, project_id)]
            if project_id is not None
            else []
        ),
    )


@router.post("/duplicates", response_model=DuplicateCheckOut)
def duplicates(session: DbSession, user: CurrentUser, data: DuplicateCheckIn):
    """Не заказывали ли это на прошлой неделе.

    Вопрос задаётся до подачи, а не после оплаты: две одинаковые заявки
    замечают обычно тогда, когда обе уже оплачены. Границу видимости
    навязывает сервер: без права видеть чужие заявки человек получит
    только свои повторы.
    """
    visible = None if has_permission(user.role, Permission.VIEW_ALL_REQUESTS) else user.id
    found = ai_memory.similar_requests(
        session, titles=data.titles, project_id=data.project_id, employee_id=visible
    )
    return DuplicateCheckOut(
        days=ai_memory.DUPLICATE_DAYS,
        requests=[
            SimilarRequestOut(
                id=r.id,
                number=r.number,
                title=r.title,
                project=r.project,
                employee=r.employee,
                status=r.status,
                days_ago=r.days_ago,
                materials=r.materials,
            )
            for r in found
        ],
    )


def _item(suggestion: ai_memory.Suggestion) -> MemoryItem:
    return MemoryItem(
        title=suggestion.title,
        unit=suggestion.unit,
        times=suggestion.times,
        last_number=suggestion.last_number,
        last_date=suggestion.last_date,
    )
