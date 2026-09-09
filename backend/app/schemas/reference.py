"""Справочники: сотрудники и объекты."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.db.models import EmployeeRole
from app.schemas.common import ORMModel


class ProjectOut(ORMModel):
    id: int
    name: str
    active: bool
    #: Сколько заявок ссылается на объект. По нему видно, можно ли объект
    #: отключать и что он вообще в работе. Заполняется роутером.
    requests_count: int = 0
    #: Потрачено по объекту за всё время — по заявкам, которые дошли
    #: хотя бы до согласования.
    spent: Decimal = Decimal("0.00")


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    active: bool = True


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None


class MaterialAdviceIn(BaseModel):
    """Что сотрудник написал в строке заявки."""

    title: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=32)


class MaterialAdviceOut(BaseModel):
    """Совет помощника. Решение остаётся за человеком."""

    #: Помощник настроен (задан ключ). False — карточку не показывать.
    enabled: bool
    #: Модель ответила. False — сбой, форма работает без подсказки.
    available: bool
    title: str
    #: Грамотное написание; совпадает с title, если править нечего.
    suggested: str | None = None
    changed: bool = False
    unit: str | None = None
    #: Такое уже заказывали — предложено написание из каталога.
    matches_existing: bool = False
    notes: list[str] = []


class AssistantStatus(BaseModel):
    enabled: bool
    model: str | None


class MaterialOut(BaseModel):
    """Подсказка для поля «что нужно»: как это называли раньше."""

    title: str
    #: Единица из последней заявки с этим названием — подставляется сама.
    unit: str | None
    #: Сколько раз встречалось: по нему подсказки идут от частых к редким.
    uses: int


class EmployeeOut(ORMModel):
    id: int
    full_name: str
    position: str
    email: str | None
    phone: str | None
    role: EmployeeRole
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
    active: bool | None = None


class TeamMemberOut(BaseModel):
    """Строка раздела «Команда»: расход сотрудника за месяц и число заявок.

    Лимитов у сотрудников нет: расход считается по объектам, а не по людям.
    """

    id: int
    full_name: str
    position: str
    spent: Decimal
    requests_count: int
