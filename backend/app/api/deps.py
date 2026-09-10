"""Зависимости FastAPI: сессия базы, текущий пользователь, проверка прав.

Здесь НЕ добавлять `from __future__ import annotations`: FastAPI не
разворачивает отложенные аннотации в зависимостях-классах.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit_context import Actor, set_actor
from app.core.permissions import Permission, has_permission, permissions_for
from app.core.security import TokenError, password_fingerprint, session_claims
from app.db.models import Employee
from app.db.session import get_session_factory
from app.services.reports import current_period


def get_db() -> Iterator[Session]:
    """Сессия на запрос. Откат при исключении, закрытие всегда."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


#: Что доступно, пока человек не сменил временный пароль. Список здесь,
#: а не проверками по роутерам: так видно всю картину и невозможно
#: забыть закрыть новый эндпоинт — то же правило, что у таблицы прав.
PASSWORD_CHANGE_ALLOWED = frozenset(
    {
        "/api/auth/me",
        "/api/auth/password",
        "/api/auth/logout",
        "/api/auth/policy",
    }
)


def get_current_user(request: Request, session: DbSession) -> Employee:
    """Текущий сотрудник по токену из httpOnly cookie.

    Роль перечитывается из базы, а не берётся из токена: понижение прав
    должно действовать сразу, а не после истечения сессии.
    """
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        raise _unauthorized("Требуется вход")

    try:
        employee_id, fingerprint = session_claims(token)
    except TokenError as exc:
        raise _unauthorized(str(exc)) from exc

    employee = session.get(Employee, employee_id)
    if employee is None or not employee.active:
        raise _unauthorized("Учётная запись недоступна")

    # Пароль сменили — все выданные до этого сессии гаснут. Это и есть
    # завершение чужих сеансов после административного сброса: cookie,
    # оставшаяся на чужом устройстве, дальше не работает.
    if fingerprint != password_fingerprint(employee.password_hash):
        raise _unauthorized("Пароль изменён, войдите заново")

    # Временный пароль знают двое, и работать под ним нельзя: заявка,
    # поданная так, не доказывает, кто её подал. Оставляем ровно то, чем
    # человек закрывает этот вопрос: увидеть себя, сменить пароль, выйти.
    if employee.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Смените временный пароль в «Параметрах» — до этого работа закрыта",
        )
    return employee


CurrentUser = Annotated[Employee, Depends(get_current_user)]


class RequirePermission:
    """Зависимость-страж: пускает только с нужным правом.

    Использование:  dependencies=[Depends(RequirePermission(Permission.X))]
    """

    def __init__(self, permission: Permission) -> None:
        self.permission = permission

    def __call__(self, user: CurrentUser) -> Employee:
        if not has_permission(user.role, self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для этого действия",
            )
        return user


async def bind_audit_actor(user: CurrentUser) -> Employee:
    """Кладёт действующего сотрудника в контекст запроса — для журнала.

    Зависимость асинхронная намеренно: синхронная выполняется в отдельном
    потоке с копией контекста, и запись до обработчика не дошла бы.
    Подключается на уровне роутера, чтобы про журнал не нужно было помнить
    в каждом новом эндпоинте.
    """
    set_actor(Actor(id=user.id, name=user.full_name, role=user.role.value))
    return user


def user_permissions(user: Employee) -> list[str]:
    return sorted(p.value for p in permissions_for(user.role))


class Period:
    """Отчётный период. По умолчанию — текущий месяц в поясе компании."""

    def __init__(
        self,
        year: int | None = Query(default=None, ge=2000, le=2100),
        month: int | None = Query(default=None, ge=1, le=12),
    ) -> None:
        default_year, default_month = current_period()
        self.year = year or default_year
        self.month = month or default_month


PeriodDep = Annotated[Period, Depends(Period)]
