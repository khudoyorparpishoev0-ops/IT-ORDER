"""Пароли и токены сессии.

Пароли — Argon2id: он устойчив к перебору на видеокартах, в отличие от
быстрых хэшей вроде SHA. Токен сессии — JWT в httpOnly cookie: скрипт на
странице его не прочитает, поэтому кража токена через XSS не срабатывает.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings
from app.core.time import utcnow

log = logging.getLogger(__name__)

_hasher = PasswordHasher()

ALGORITHM = "HS256"

#: Минимальная длина пароля. Короче — подбирается за разумное время.
MIN_PASSWORD_LENGTH = 10


class TokenError(Exception):
    """Токен отсутствует, испорчен или просрочен."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль. Любая ошибка разбора хэша — это «не совпало»,
    а не исключение наружу: иначе битая запись роняет вход целиком.

    UnicodeEncodeError ловим отдельно: argon2 кодирует хэш в ASCII, и
    нелатинский мусор в колонке падает ещё до разбора.
    """
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError, UnicodeEncodeError, ValueError):
        log.warning("Повреждённый хэш пароля в базе")
        return False


def needs_rehash(password_hash: str) -> bool:
    """Параметры Argon2 со временем ужесточаются — хэш стоит обновить
    при следующем успешном входе."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, UnicodeEncodeError, ValueError):
        return True


#: Тип токена в поле `typ`. Сессионный токен и промежуточный токен второго
#: фактора не должны подменять друг друга: иначе первый шаг входа давал бы
#: полный доступ.
TOKEN_SESSION = "session"
TOKEN_PENDING_2FA = "pending_2fa"

#: Промежуточный токен живёт минуты: он лишь удерживает шаг входа.
PENDING_2FA_MINUTES = 10


def create_token(subject: int, *, role: str) -> str:
    """Токен сессии. `sub` — id сотрудника, `role` — для быстрой проверки
    на фронтенде; сервер всё равно перечитывает роль из базы."""
    settings = get_settings()
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "typ": TOKEN_SESSION,
        "iat": now,
        "exp": now + timedelta(minutes=settings.session_lifetime_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_pending_2fa_token(subject: int) -> str:
    """Токен между первым и вторым фактором. Доступа к данным не даёт."""
    settings = get_settings()
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": TOKEN_PENDING_2FA,
        "iat": now,
        "exp": now + timedelta(minutes=PENDING_2FA_MINUTES),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Сессия истекла, войдите заново") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Недействительный токен сессии") from exc


def token_subject(token: str, *, expected_type: str = TOKEN_SESSION) -> int:
    """Идентификатор из токена с проверкой его назначения.

    Без проверки `typ` промежуточный токен первого шага открывал бы
    систему целиком, минуя второй фактор.
    """
    payload = decode_token(token)
    if payload.get("typ") != expected_type:
        raise TokenError("Токен не подходит для этого действия")
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("В токене нет идентификатора пользователя") from exc


def validate_password_strength(password: str) -> None:
    """Минимальные требования. Сложные правила заменяем длиной:
    длинная фраза надёжнее коротких «Passw0rd!»."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Пароль короче {MIN_PASSWORD_LENGTH} символов. "
            "Возьмите фразу подлиннее, её проще запомнить и труднее подобрать."
        )
    if password.strip() != password:
        raise ValueError("Пароль не должен начинаться или заканчиваться пробелом")
