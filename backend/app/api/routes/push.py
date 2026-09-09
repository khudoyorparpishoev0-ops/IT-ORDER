"""Push-уведомления в браузер: подписка устройства и проверка."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, bind_audit_actor
from app.config import get_settings
from app.core.errors import ValidationError
from app.core.push import Notification, PushError, public_key, send
from app.db.models import PushSubscription
from app.schemas.push import PushConfigOut, PushSubscribeIn, PushUnsubscribeIn
from app.services import push_notify as svc
from app.services.notifications import panel_url
from sqlalchemy import select

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/push", tags=["push"], dependencies=[Depends(bind_audit_actor)]
)


def _config(session: DbSession, user: CurrentUser) -> PushConfigOut:
    settings = get_settings()
    key: str | None = None
    if settings.push_enabled:
        try:
            key = public_key()
        except PushError as exc:
            # Ключ задан, но битый: панели скажем «выключено», а причину — в лог.
            log.error("Push выключен: %s", exc)
    return PushConfigOut(
        enabled=key is not None,
        public_key=key,
        devices=svc.devices(session, user),
    )


@router.get("/config", response_model=PushConfigOut)
def config(session: DbSession, user: CurrentUser):
    return _config(session, user)


@router.post("/subscribe", response_model=PushConfigOut, status_code=status.HTTP_201_CREATED)
def subscribe(session: DbSession, user: CurrentUser, data: PushSubscribeIn):
    svc.subscribe(session, user, data)
    return _config(session, user)


@router.post("/unsubscribe", response_model=PushConfigOut)
def unsubscribe(session: DbSession, user: CurrentUser, data: PushUnsubscribeIn):
    svc.unsubscribe(session, user, data.endpoint)
    return _config(session, user)


@router.post("/test", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def test(session: DbSession, user: CurrentUser) -> None:
    """Проверочное уведомление на все устройства сотрудника.

    Ошибка идёт наружу: человек нажал кнопку и должен увидеть, почему
    не пришло, — в отличие от уведомлений о заявках, где сбой push не
    должен мешать делу.
    """
    if not get_settings().push_enabled:
        raise ValidationError("Push не настроен: задайте VAPID_PRIVATE_KEY")
    subscriptions = session.scalars(
        select(PushSubscription).where(PushSubscription.employee_id == user.id)
    ).all()
    if not subscriptions:
        raise ValidationError("На этом устройстве уведомления ещё не включены")
    try:
        for sub in subscriptions:
            send(
                Notification(
                    subscription=sub.info(),
                    title="HONA ORDER",
                    body="Проверка: уведомления на этом устройстве работают.",
                    url=panel_url("/settings"),
                    tag="push-test",
                )
            )
    except PushError as exc:
        raise ValidationError(str(exc)) from exc
