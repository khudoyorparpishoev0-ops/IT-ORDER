"""Схемы входа, второго фактора и профиля."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models import EmployeeRole


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TwoFactorIn(BaseModel):
    """Код из приложения-аутентификатора либо код восстановления."""

    code: str = Field(min_length=1, max_length=32)


class LoginResult(BaseModel):
    """Итог первого шага.

    `status`:
      - `ok` — вход завершён, сессия выдана;
      - `2fa_required` — нужен код из приложения;
      - `2fa_setup_required` — роль обязывает включить второй фактор,
        а он ещё не настроен.
    """

    status: str
    user: CurrentUserOut | None = None


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
    two_factor_enabled: bool
    two_factor_required: bool
    recovery_codes_left: int
    notifications: NotificationPrefsOut


class TotpSetupOut(BaseModel):
    """Данные для настройки: секрет, ссылка otpauth и QR в SVG."""

    secret: str
    uri: str
    qr_svg: str


class TotpConfirmIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class RecoveryCodesOut(BaseModel):
    """Показываются один раз: в базе хранятся только хэши."""

    codes: list[str]


class PasswordConfirmIn(BaseModel):
    """Действие, требующее подтверждения паролем."""

    password: str = Field(min_length=1, max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PasswordSetIn(BaseModel):
    """Назначение пароля администратором.

    Код второго фактора обязателен: смена чужого пароля — это захват
    учётной записи, и подтверждать её должен человек, а не открытая
    сессия.
    """

    password: str = Field(min_length=1, max_length=256)
    #: Код из приложения администратора или его код восстановления.
    totp_code: str = Field(min_length=1, max_length=32)


class ConfirmIn(BaseModel):
    """Подтверждение опасного действия кодом второго фактора."""

    totp_code: str = Field(min_length=1, max_length=32)


class AuthPolicyOut(BaseModel):
    """Публичная политика входа — нужна экрану входа до авторизации."""

    email_domains: list[str]
    domains_hint: str
    #: Работает ли восстановление пароля. Без настроенной почты письмо
    #: отправить некуда, и предлагать эту кнопку не нужно.
    password_reset_available: bool


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=2048)
    new_password: str = Field(min_length=1, max_length=256)


class NotificationPrefsIn(BaseModel):
    new_requests: bool | None = None
    stale_requests: bool | None = None
    weekly_budget: bool | None = None


class NotificationPrefsOut(BaseModel):
    new_requests: bool
    stale_requests: bool
    weekly_budget: bool
    #: false — почта не настроена, письма не уйдут при любых переключателях.
    mail_configured: bool


LoginResult.model_rebuild()
