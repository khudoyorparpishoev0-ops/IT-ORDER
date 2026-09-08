"""Настройки: строка подключения и обязательные значения."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

import pytest

from app.config import Settings


def build(**kwargs) -> Settings:
    base = dict(
        app_env="development",
        secret_key="x",
        postgres_host="db",
        postgres_port=5432,
        postgres_user="hona",
        postgres_db="hona_core",
    )
    return Settings(**{**base, **kwargs})


@pytest.mark.parametrize(
    "password",
    [
        "prostoi",
        # openssl rand -base64 почти всегда даёт «/», «+» и «=»,
        # а они значимы в URL: «/» обрывает адрес хоста.
        "with/slash",
        "with+plus",
        "ends=with=equals",
        "Xy9/kL+mN2op==",
        "p@ss:word",
        "пароль/кириллицей",
    ],
)
def test_password_survives_dsn(password: str) -> None:
    parsed = urlsplit(build(postgres_password=password).database_url)
    assert unquote(parsed.password or "") == password
    assert parsed.hostname == "db"
    assert parsed.port == 5432
    assert parsed.path == "/hona_core"


def test_username_is_escaped() -> None:
    parsed = urlsplit(build(postgres_user="user@corp", postgres_password="x").database_url)
    assert unquote(parsed.username or "") == "user@corp"


def test_unix_socket_host_is_escaped() -> None:
    """Путь к сокету начинается со «/» и тоже требует экранирования."""
    url = build(postgres_host="/var/run/postgresql", postgres_password="x").database_url
    assert "%2Fvar%2Frun%2Fpostgresql" in url


def test_production_requires_secret_key() -> None:
    with pytest.raises(ValueError):
        Settings(app_env="production", secret_key="")


def test_smtp_security_must_be_known() -> None:
    with pytest.raises(ValueError):
        build(postgres_password="x", smtp_security="tls")


def test_mail_disabled_without_credentials() -> None:
    assert not build(postgres_password="x", smtp_user="", smtp_password="").mail_enabled


def test_mail_sender_falls_back_to_user() -> None:
    settings = build(
        postgres_password="x", smtp_user="order@ithona.tj", smtp_password="y", mail_from=""
    )
    assert settings.mail_sender == "order@ithona.tj"


def test_windows_line_endings_do_not_leak_into_values() -> None:
    """`.env` переносят через Windows, и значения приезжают с «\\r».

    Невидимый символ ломал ровно то, что труднее всего диагностировать:
    токен бота становился на символ длиннее и Telegram отвечал «malformed
    URL», а SMTP отказывал в логине при верном пароле.
    """
    settings = build(
        postgres_password="x",
        telegram_bot_token="123456:AAHtest\r",
        smtp_password="пароль-приложения\r",
        public_base_url=" https://order.ithona.tj \r",
    )
    assert settings.telegram_bot_token == "123456:AAHtest"
    assert settings.smtp_password == "пароль-приложения"
    assert settings.public_base_url == "https://order.ithona.tj"
