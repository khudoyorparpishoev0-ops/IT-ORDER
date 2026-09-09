"""Помощник по заявке. Только советы: ничего не создаёт и не меняет."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, bind_audit_actor
from app.schemas.assistant import AssistantAskIn, AssistantReplyOut
from app.services import request_assistant

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
    context = data.context.model_copy(update={"employee_name": user.full_name})
    return request_assistant.converse(
        session, text=data.text, history=data.history, context=context
    )
