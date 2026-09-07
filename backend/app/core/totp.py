"""Двухфакторная аутентификация по TOTP (RFC 6238).

Второй фактор — приложение-аутентификатор на телефоне (Google Authenticator,
Aegis, 1Password и любое другое). Коды на почту не шлём: почта здесь первый
фактор, и второй фактор из того же канала защищает только от подсмотренного
пароля, но не от взломанного ящика.

Секрет в базе хранится зашифрованным. Ключ выводится из SECRET_KEY, поэтому
утечка одного лишь дампа базы не даёт возможности генерировать чужие коды.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import secrets

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from qrcode.image.svg import SvgPathImage

from app.config import get_settings

log = logging.getLogger(__name__)

#: Кодов восстановления — на случай потери телефона.
RECOVERY_CODE_COUNT = 10
#: Длина половины кода: получается вид «a1b2c3-d4e5f6», удобный для записи.
RECOVERY_HALF = 6

#: Допуск в один шаг (30 с) в обе стороны: часы телефона и сервера расходятся.
VALID_WINDOW = 1


class TotpError(Exception):
    """Код не подошёл или секрет повреждён."""


def _fernet() -> Fernet:
    """Ключ шифрования секретов, выведенный из SECRET_KEY.

    Отдельная соль отделяет его от других применений SECRET_KEY: подпись
    сессий и шифрование секретов не должны использовать один и тот же ключ.
    """
    secret = get_settings().secret_key or "development-only-key"
    digest = hashlib.sha256(f"totp-secret-encryption:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def generate_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        # Сменили SECRET_KEY или повреждена запись: восстановить нельзя,
        # администратор должен сбросить второй фактор сотруднику.
        raise TotpError(
            "Не удалось прочитать секрет второго фактора. Обратитесь "
            "к администратору, чтобы настроить его заново."
        ) from exc


def provisioning_uri(secret: str, email: str) -> str:
    """Ссылка otpauth:// для приложения-аутентификатора."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=email, issuer_name=get_settings().totp_issuer
    )


def qr_svg(uri: str) -> str:
    """QR-код в SVG. Растр не используем: Pillow в образе не нужен,
    а вектор чётко печатается и масштабируется."""
    image = qrcode.make(uri, image_factory=SvgPathImage, box_size=10, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode()


def verify_code(secret: str, code: str) -> bool:
    """Проверяет одноразовый код с допуском на расхождение часов."""
    cleaned = "".join(ch for ch in code if ch.isdigit())
    if len(cleaned) != 6:
        return False
    return pyotp.TOTP(secret).verify(cleaned, valid_window=VALID_WINDOW)


def current_step(secret: str, code: str) -> int | None:
    """Номер временного шага, которому соответствует код.

    Нужен, чтобы запомнить использованный код: без этого подсмотренный
    код можно применить второй раз в пределах его 30-секундного окна.
    """
    cleaned = "".join(ch for ch in code if ch.isdigit())
    totp = pyotp.TOTP(secret)
    import time

    now = int(time.time())
    for offset in range(-VALID_WINDOW, VALID_WINDOW + 1):
        step = now // totp.interval + offset
        if secrets.compare_digest(totp.generate_otp(step), cleaned):
            return step
    return None


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Коды восстановления вида «a1b2c3-d4e5f6»."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # без похожих 0/o, 1/l/i

    def half() -> str:
        return "".join(secrets.choice(alphabet) for _ in range(RECOVERY_HALF))

    return [f"{half()}-{half()}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    """Коды хранятся хэшированными: дамп базы не должен давать вход.

    Argon2 здесь избыточен — код случайный и длинный, перебор бессмыслен,
    а быстрый хэш позволяет проверить сразу все коды сотрудника.
    """
    secret = get_settings().secret_key or "development-only-key"
    normalized = normalize_recovery_code(code)
    return hashlib.sha256(f"{secret}:{normalized}".encode()).hexdigest()


def normalize_recovery_code(code: str) -> str:
    """Пользователь может ввести код с пробелами, в верхнем регистре
    или без дефиса — принимаем все варианты."""
    return "".join(ch for ch in code.lower() if ch.isalnum())
