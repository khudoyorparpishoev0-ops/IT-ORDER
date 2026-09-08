"""Схемы привязки Telegram."""

from __future__ import annotations

from pydantic import BaseModel


class TelegramStatusOut(BaseModel):
    """Что показать в «Параметрах»."""

    #: Бот настроен администратором сервера: есть токен и имя бота.
    configured: bool
    #: Этот сотрудник уже привязал свой чат.
    linked: bool
    #: @имя в Telegram, если известно.
    username: str | None
    bot_username: str | None


class TelegramLinkOut(BaseModel):
    """Одноразовая ссылка на бота."""

    url: str
    expires_in_minutes: int


class TelegramSetupOut(BaseModel):
    """Итог настройки вебхука — показываем администратору."""

    #: Адрес, который теперь знает Telegram. Секрет внутри, наружу его
    #: видит только администратор, который и так знает SECRET_KEY.
    webhook_url: str
    bot_username: str | None
