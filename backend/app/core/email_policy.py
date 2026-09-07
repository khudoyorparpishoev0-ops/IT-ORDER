"""Политика корпоративной почты.

Войти в систему и быть заведённым может только адрес из корпоративного
домена. Это отсекает личные ящики: почта здесь одновременно логин и способ
подтвердить, что человек работает в компании.
"""

from __future__ import annotations

from app.config import get_settings


class EmailPolicyError(ValueError):
    """Адрес не проходит корпоративную политику."""


def normalize(email: str) -> str:
    """Приводит адрес к каноническому виду: регистр в почте не значим."""
    return email.strip().lower()


def domain_of(email: str) -> str:
    _, _, domain = normalize(email).partition("@")
    return domain


def is_corporate(email: str) -> bool:
    domains = get_settings().email_domains
    if not domains:
        # Ограничение снято настройкой — проверять нечего.
        return True
    return domain_of(email) in domains


def ensure_corporate(email: str) -> str:
    """Проверяет адрес и возвращает нормализованный. Иначе — ошибка."""
    value = normalize(email)
    if "@" not in value:
        raise EmailPolicyError("Это не похоже на адрес электронной почты")
    if not is_corporate(value):
        allowed = ", ".join(f"@{d}" for d in get_settings().email_domains)
        raise EmailPolicyError(
            f"Вход только с корпоративной почты: {allowed}. "
            "Личные ящики не подходят."
        )
    return value


def allowed_domains_hint() -> str:
    """Подсказка для интерфейса: «@ithona.tj»."""
    domains = get_settings().email_domains
    return ", ".join(f"@{d}" for d in domains) if domains else ""
