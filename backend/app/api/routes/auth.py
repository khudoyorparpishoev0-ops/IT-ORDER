"""Вход, выход, профиль, смена пароля."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession, user_permissions
from app.config import get_settings
from app.core.security import create_token
from app.db.models import Employee
from app.schemas.auth import CurrentUserOut, LoginIn, PasswordChangeIn
from app.services import auth as svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _to_out(employee: Employee) -> CurrentUserOut:
    return CurrentUserOut(
        id=employee.id,
        full_name=employee.full_name,
        position=employee.position,
        email=employee.email,
        role=employee.role,
        permissions=user_permissions(employee),
        last_login_at=employee.last_login_at,
    )


def _set_session_cookie(response: Response, employee: Employee) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=create_token(employee.id, role=employee.role.value),
        max_age=settings.session_lifetime_minutes * 60,
        # httponly закрывает токен от скриптов на странице: украсть его
        # через XSS не выйдет.
        httponly=True,
        # samesite=lax отсекает межсайтовые POST — защита от CSRF.
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/login", response_model=CurrentUserOut)
def login(session: DbSession, data: LoginIn, response: Response):
    employee = svc.authenticate(session, data.email, data.password)
    _set_session_cookie(response, employee)
    return _to_out(employee)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(response: Response) -> Response:
    settings = get_settings()
    response.delete_cookie(
        key=settings.cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=CurrentUserOut)
def me(user: CurrentUser):
    return _to_out(user)


@router.post("/password", response_model=CurrentUserOut)
def change_password(session: DbSession, user: CurrentUser, data: PasswordChangeIn):
    """Смена собственного пароля. Требует текущий пароль."""
    employee = svc.change_own_password(
        session, user, data.current_password, data.new_password
    )
    return _to_out(employee)
