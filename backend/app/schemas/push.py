"""Схемы push-уведомлений в браузер."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PushConfigOut(BaseModel):
    """Что показать в «Параметрах» и чем подписать браузер."""

    #: Администратор сервера задал ключ VAPID.
    enabled: bool
    #: Открытый ключ для `pushManager.subscribe`. Пусто, если выключено.
    public_key: str | None
    #: Сколько устройств у этого сотрудника уже подписано.
    devices: int


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=128)
    auth: str = Field(min_length=1, max_length=64)


class PushSubscribeIn(BaseModel):
    """Подписка в том виде, в каком её отдаёт браузер (`toJSON()`)."""

    endpoint: str = Field(min_length=1, max_length=2000)
    keys: PushKeys
    #: Чем подписались: браузер сам скажет, человеку вводить ничего не нужно.
    user_agent: str | None = Field(default=None, max_length=200)


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
