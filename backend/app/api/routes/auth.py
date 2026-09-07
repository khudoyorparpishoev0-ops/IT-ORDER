"""Вход, второй фактор, профиль, пароли."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, DbSession, user_permissions
from app.config import get_settings
from app.core.email_policy import allowed_domains_hint
from app.core.security import (
    TOKEN_PENDING_2FA,
    PENDING_2FA_MINUTES,
    TokenError,
    create_pending_2fa_token,
    create_token,
    token_subject,
)
from app.db.models import Employee
from app.core.mail import send_quietly
from app.schemas.auth import (
    AuthPolicyOut,
    NotificationPrefsIn,
    NotificationPrefsOut,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    CurrentUserOut,
    LoginIn,
    LoginResult,
    PasswordChangeIn,
    PasswordConfirmIn,
    RecoveryCodesOut,
    TotpConfirmIn,
    TotpSetupOut,
    TwoFactorIn,
)
from app.services import auth as svc
from app.services.audit import write_audit
from app.services import mail_templates as templates
from app.services.notifications import panel_url

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _to_out(session, employee: Employee) -> CurrentUserOut:
    return CurrentUserOut(
        id=employee.id,
        full_name=employee.full_name,
        position=employee.position,
        email=employee.email,
        role=employee.role,
        permissions=user_permissions(employee),
        last_login_at=employee.last_login_at,
        two_factor_enabled=employee.totp_enabled,
        two_factor_required=svc.requires_2fa(employee),
        recovery_codes_left=svc.unused_recovery_count(session, employee),
        notifications=_prefs(employee),
    )


def _prefs(employee: Employee) -> NotificationPrefsOut:
    return NotificationPrefsOut(
        new_requests=employee.notify_new_requests,
        stale_requests=employee.notify_stale_requests,
        weekly_budget=employee.notify_weekly_budget,
        mail_configured=get_settings().mail_enabled,
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


def _set_pending_cookie(response: Response, employee: Employee) -> None:
    settings = get_settings()
    response.set_cookie(
        key=_pending_cookie_name(),
        value=create_pending_2fa_token(employee.id),
        max_age=PENDING_2FA_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_pending_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=_pending_cookie_name(),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _pending_cookie_name() -> str:
    return f"{get_settings().cookie_name}_pending"


def _pending_employee(request: Request, session) -> Employee:
    """Сотрудник, прошедший первый фактор. Токен другого типа не подойдёт."""
    token = request.cookies.get(_pending_cookie_name())
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Шаг входа истёк. Введите почту и пароль заново.",
        )
    try:
        employee_id = token_subject(token, expected_type=TOKEN_PENDING_2FA)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    employee = session.get(Employee, employee_id)
    if employee is None or not employee.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Учётная запись недоступна"
        )
    return employee


@router.get("/policy", response_model=AuthPolicyOut)
def policy():
    """Политика входа для экрана авторизации. Открыта: показывает лишь то,
    что и так написано на визитке компании."""
    settings = get_settings()
    return AuthPolicyOut(
        email_domains=list(settings.email_domains),
        domains_hint=allowed_domains_hint(),
        password_reset_available=settings.mail_enabled,
    )


@router.post("/login", response_model=LoginResult)
def login(session: DbSession, data: LoginIn, response: Response):
    try:
        employee = svc.authenticate(session, data.email, data.password)
    except svc.TwoFactorRequired as step:
        # Начат вход под другой учётной записью — прежняя сессия в этом
        # браузере больше не действует, иначе непонятно, от чьего имени
        # выполняются следующие шаги.
        _clear_session_cookie(response)
        _set_pending_cookie(response, step.employee)
        return LoginResult(
            status="2fa_setup_required" if step.setup_required else "2fa_required"
        )

    _set_session_cookie(response, employee)
    _clear_pending_cookie(response)
    return LoginResult(status="ok", user=_to_out(session, employee))


@router.post("/2fa", response_model=LoginResult)
def submit_second_factor(
    request: Request, session: DbSession, data: TwoFactorIn, response: Response
):
    """Второй шаг входа: код из приложения или код восстановления."""
    employee = _pending_employee(request, session)
    employee = svc.verify_second_factor(session, employee, data.code)
    _set_session_cookie(response, employee)
    _clear_pending_cookie(response)
    return LoginResult(status="ok", user=_to_out(session, employee))


@router.post("/2fa/setup", response_model=TotpSetupOut)
def start_setup(request: Request, session: DbSession):
    """Начало настройки второго фактора.

    Доступно и вошедшему, и тому, кто застрял на обязательной настройке
    после первого шага, — иначе он не смог бы её пройти.
    """
    employee = _current_or_pending(request, session)
    return TotpSetupOut(**svc.start_totp_setup(session, employee))


@router.post("/2fa/confirm", response_model=RecoveryCodesOut)
def confirm_setup(
    request: Request, session: DbSession, data: TotpConfirmIn, response: Response
):
    """Подтверждение кодом. Возвращает коды восстановления — показываются
    один раз, в базе хранятся только хэши."""
    employee = _current_or_pending(request, session)
    codes = svc.confirm_totp_setup(session, employee, data.code)
    # Настройка завершена — сразу выдаём сессию, повторный вход не нужен.
    svc.complete_login(session, employee)
    _set_session_cookie(response, employee)
    _clear_pending_cookie(response)
    return RecoveryCodesOut(codes=codes)


def _current_or_pending(request: Request, session) -> Employee:
    """Чей второй фактор настраиваем.

    Незавершённый вход важнее действующей сессии: если в браузере остался
    сеанс другого сотрудника, настройка должна относиться к тому, кто
    сейчас входит, а не к тому, кто вошёл раньше.
    """
    from app.api.deps import get_current_user

    if request.cookies.get(_pending_cookie_name()):
        return _pending_employee(request, session)
    return get_current_user(request, session)


@router.post("/2fa/recovery-codes", response_model=RecoveryCodesOut)
def reissue_recovery_codes(
    session: DbSession, user: CurrentUser, data: PasswordConfirmIn
):
    return RecoveryCodesOut(
        codes=svc.regenerate_recovery_codes(session, user, data.password)
    )


@router.post("/2fa/disable", response_model=CurrentUserOut)
def disable_second_factor(
    session: DbSession, user: CurrentUser, data: PasswordConfirmIn
):
    svc.disable_totp(session, user, data.password)
    return _to_out(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(request: Request, session: DbSession, response: Response) -> Response:
    """Выход. Записывает в журнал, если сессия ещё действительна.

    Требовать действующую сессию нельзя: у истёкшего токена выход должен
    всё равно очистить cookie, иначе браузер останется с мусором.
    """
    employee = _employee_from_session(request, session)
    if employee is not None:
        write_audit(
            session,
            entity="employee",
            entity_id=employee.id,
            action="logout",
            employee=employee,
        )
    _clear_session_cookie(response)
    _clear_pending_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _employee_from_session(request: Request, session) -> Employee | None:
    """Сотрудник по cookie сессии — молча, без 401."""
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        return None
    try:
        employee_id = token_subject(token)
    except TokenError:
        return None
    return session.get(Employee, employee_id)


@router.get("/me", response_model=CurrentUserOut)
def me(session: DbSession, user: CurrentUser):
    return _to_out(session, user)


@router.post("/password", response_model=CurrentUserOut)
def change_password(session: DbSession, user: CurrentUser, data: PasswordChangeIn):
    """Смена собственного пароля. Требует текущий пароль."""
    employee = svc.change_own_password(
        session, user, data.current_password, data.new_password
    )
    return _to_out(session, employee)


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def request_password_reset(
    session: DbSession,
    data: PasswordResetRequestIn,
    background: BackgroundTasks,
    response: Response,
) -> Response:
    """Отправляет ссылку восстановления.

    Ответ одинаков для существующего и несуществующего адреса: разный
    выдал бы, кто заведён в системе.
    """
    prepared = svc.build_password_reset(session, data.email)
    if prepared is not None:
        employee, token = prepared
        letter = templates.password_reset(
            full_name=employee.full_name,
            url=panel_url(f"/reset-password?token={token}"),
        )
        letter.to = employee.email or ""
        # В фоне: отправку письма клиент ждать не должен, а неудача
        # не меняет ответ — иначе по нему станет видно, кто заведён.
        background.add_task(send_quietly, letter)

    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/password-reset/confirm", response_model=CurrentUserOut)
def confirm_password_reset(session: DbSession, data: PasswordResetConfirmIn):
    """Ставит новый пароль по ссылке из письма.

    Сессию не выдаёт: второй фактор остаётся на месте, и войти по одному
    лишь доступу к почте нельзя.
    """
    employee = svc.apply_password_reset(session, data.token, data.new_password)
    return _to_out(session, employee)


@router.patch("/notifications", response_model=CurrentUserOut)
def update_notifications(
    session: DbSession, user: CurrentUser, data: NotificationPrefsIn
):
    changes = data.model_dump(exclude_unset=True)
    mapping = {
        "new_requests": "notify_new_requests",
        "stale_requests": "notify_stale_requests",
        "weekly_budget": "notify_weekly_budget",
    }
    for key, value in changes.items():
        if value is not None:
            setattr(user, mapping[key], value)
    session.flush()
    return _to_out(session, user)
