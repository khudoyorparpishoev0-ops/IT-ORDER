"""Справочники: сотрудники и объекты."""

from __future__ import annotations

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


class EmployeeCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    position: str = Field(default="", max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    role: EmployeeRole = EmployeeRole.EMPLOYEE
    monthly_limit: Decimal | None = Field(default=None, ge=0)
    active: bool = True


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
