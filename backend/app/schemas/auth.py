"""Схемы входа и профиля."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models import EmployeeRole


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class CurrentUserOut(BaseModel):
    """Кто вошёл и что ему можно. Фронтенд по этому прячет разделы;
    сервер всё равно проверяет права на каждом запросе."""

    id: int
    full_name: str
    position: str
    email: str | None
    role: EmployeeRole
    permissions: list[str]
    last_login_at: datetime | None


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PasswordSetIn(BaseModel):
    """Назначение пароля администратором."""

    password: str = Field(min_length=1, max_length=256)
