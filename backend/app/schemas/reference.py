"""Справочники: сотрудники и объекты."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.models import EmployeeRole
from app.schemas.common import ORMModel


class ProjectOut(ORMModel):
    id: int
    name: str
    active: bool


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    active: bool = True


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None


class EmployeeOut(ORMModel):
    id: int
    full_name: str
    position: str
    email: str | None
    phone: str | None
    role: EmployeeRole
    monthly_limit: Decimal | None
    active: bool


class EmployeeAccessOut(BaseModel):
    """Состояние доступа сотрудника: кто может войти, у кого включён второй
    фактор, кого заблокировал перебор.

    Отдельная схема, а не поля в EmployeeOut: список сотрудников читает
    любой вошедший — он нужен, чтобы заполнить заявку. Знать, у кого нет
    второго фактора и когда он последний раз входил, коллегам незачем,
    поэтому эти данные отдаются только по праву MANAGE_REFERENCE.
    """

    id: int
    #: Активен, есть почта и задан пароль — только тогда вход возможен.
    can_sign_in: bool
    has_password: bool
    two_factor_enabled: bool
    #: Роль обязывает включить второй фактор при первом входе.
    two_factor_required: bool
    recovery_codes_left: int
    last_login_at: datetime | None
    #: Заполнено — вход закрыт до этого времени после неудачных попыток.
    locked_until: datetime | None


class EmployeeCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    position: str = Field(default="", max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    role: EmployeeRole = EmployeeRole.EMPLOYEE
    monthly_limit: Decimal | None = Field(default=None, ge=0)
    active: bool = True
    #: Пароль для входа. Задаётся вместе с карточкой намеренно: два
    #: запроса подряд оставляли сотрудника заведённым, но без доступа,
    #: если второй не проходил. Пустое значение — доступ выдадут позже.
    password: str | None = Field(default=None, max_length=200)


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    position: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    role: EmployeeRole | None = None
    monthly_limit: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


class TeamMemberOut(BaseModel):
    """Строка раздела «Команда»: лимит, расход за месяц и доля."""

    id: int
    full_name: str
    position: str
    limit: Decimal | None
    spent: Decimal
    #: Доля израсходованного, 0..100. None, если лимит не задан.
    pct: int | None
    requests_count: int

    @field_validator("pct")
    @classmethod
    def clamp(cls, v: int | None) -> int | None:
        return None if v is None else max(0, min(100, v))
