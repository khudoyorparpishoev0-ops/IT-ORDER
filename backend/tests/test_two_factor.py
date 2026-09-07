"""Двухфакторная аутентификация."""

from __future__ import annotations

import time

import pyotp
import pytest

from app.core.security import (
    TOKEN_PENDING_2FA,
    TokenError,
    create_pending_2fa_token,
    create_token,
    token_subject,
)
from app.core.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    normalize_recovery_code,
    provisioning_uri,
    qr_svg,
    verify_code,
)
from app.db.models import EmployeeRole
from tests.conftest import TEST_PASSWORD


def code_for(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def next_code(secret: str) -> str:
    """Код следующего 30-секундного шага.

    Сервер принимает соседние шаги (часы телефона расходятся с сервером),
    поэтому такой код валиден — но отличается от только что использованного.
    Иначе тест ждал бы полминуты на каждый вход.
    """
    return pyotp.TOTP(secret).at(time.time() + 30)


def setup_2fa(client, person) -> tuple[str, list[str]]:
    """Проходит настройку до конца, возвращает секрет и коды восстановления."""
    setup = client.post("/api/auth/2fa/setup").json()
    secret = setup["secret"]
    confirmed = client.post(
        "/api/auth/2fa/confirm", json={"code": code_for(secret)}
    )
    assert confirmed.status_code == 200, confirmed.text
    return secret, confirmed.json()["codes"]


# --------------------------------------------------------------------------
# Криптография
# --------------------------------------------------------------------------
def test_secret_is_encrypted_at_rest() -> None:
    """Дамп базы не должен давать возможность генерировать чужие коды."""
    secret = generate_secret()
    stored = encrypt_secret(secret)
    assert secret not in stored
    assert decrypt_secret(stored) == secret


def test_encryption_is_not_deterministic() -> None:
    secret = generate_secret()
    assert encrypt_secret(secret) != encrypt_secret(secret)


def test_verify_code() -> None:
    secret = generate_secret()
    assert verify_code(secret, code_for(secret))
    assert not verify_code(secret, "000000")
    assert not verify_code(secret, "abc")
    assert not verify_code(secret, "12345")


def test_provisioning_uri_and_qr() -> None:
    secret = generate_secret()
    uri = provisioning_uri(secret, "i.petrov@it-hona.tj")
    assert uri.startswith("otpauth://totp/")
    assert secret in uri
    svg = qr_svg(uri)
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg


def test_recovery_codes_are_unique_and_hashed() -> None:
    codes = generate_recovery_codes(10)
    assert len(set(codes)) == 10
    assert all("-" in c for c in codes)
    digest = hash_recovery_code(codes[0])
    assert codes[0] not in digest


def test_recovery_code_input_is_forgiving() -> None:
    """Пользователь вводит код с телефона: регистр и дефис не должны мешать."""
    code = "ab12cd-ef34gh"
    assert normalize_recovery_code(" AB12CD-EF34GH ") == normalize_recovery_code(code)
    assert hash_recovery_code(" AB12CD-EF34GH ") == hash_recovery_code(code)


# --------------------------------------------------------------------------
# Токены
# --------------------------------------------------------------------------
def test_pending_token_cannot_open_session() -> None:
    """Иначе первый шаг входа давал бы полный доступ, минуя второй фактор."""
    pending = create_pending_2fa_token(7)
    with pytest.raises(TokenError):
        token_subject(pending)
    assert token_subject(pending, expected_type=TOKEN_PENDING_2FA) == 7


def test_session_token_is_not_accepted_as_pending() -> None:
    session_token = create_token(7, role="admin")
    with pytest.raises(TokenError):
        token_subject(session_token, expected_type=TOKEN_PENDING_2FA)


# --------------------------------------------------------------------------
# Настройка
# --------------------------------------------------------------------------
def test_setup_does_not_enable_until_confirmed(client, login, employee) -> None:
    """Ошибка при настройке не должна запирать человека снаружи."""
    login(employee)
    client.post("/api/auth/2fa/setup")
    assert client.get("/api/auth/me").json()["two_factor_enabled"] is False


def test_confirm_with_wrong_code_is_401(client, login, employee) -> None:
    login(employee)
    client.post("/api/auth/2fa/setup")
    assert (
        client.post("/api/auth/2fa/confirm", json={"code": "000000"}).status_code == 401
    )


def test_confirm_enables_and_issues_recovery_codes(client, login, employee) -> None:
    login(employee)
    _, codes = setup_2fa(client, employee)
    assert len(codes) == 10

    me = client.get("/api/auth/me").json()
    assert me["two_factor_enabled"] is True
    assert me["recovery_codes_left"] == 10


def test_confirm_without_setup_is_409(client, login, employee) -> None:
    login(employee)
    assert (
        client.post("/api/auth/2fa/confirm", json={"code": "123456"}).status_code == 409
    )


# --------------------------------------------------------------------------
# Вход в два шага
# --------------------------------------------------------------------------
def test_login_requires_code_when_enabled(client, login, employee) -> None:
    login(employee)
    secret, _ = setup_2fa(client, employee)
    client.post("/api/auth/logout")

    first = client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert first.json()["status"] == "2fa_required"
    assert first.json()["user"] is None
    # Промежуточный токен не даёт доступа к данным
    assert client.get("/api/requests").status_code == 401

    second = client.post("/api/auth/2fa", json={"code": next_code(secret)})
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "ok"
    assert client.get("/api/requests").status_code == 200


def test_wrong_code_does_not_open_session(client, login, employee) -> None:
    login(employee)
    setup_2fa(client, employee)
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert client.post("/api/auth/2fa", json={"code": "000000"}).status_code == 401
    assert client.get("/api/requests").status_code == 401


def test_code_cannot_be_replayed(client, login, employee) -> None:
    """Подсмотренный код не должен срабатывать второй раз в своём окне."""
    login(employee)
    secret, _ = setup_2fa(client, employee)
    client.post("/api/auth/logout")

    code = next_code(secret)
    client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert client.post("/api/auth/2fa", json={"code": code}).status_code == 200

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert client.post("/api/auth/2fa", json={"code": code}).status_code == 401


def test_second_factor_without_first_is_401(client) -> None:
    assert client.post("/api/auth/2fa", json={"code": "123456"}).status_code == 401


# --------------------------------------------------------------------------
# Коды восстановления
# --------------------------------------------------------------------------
def test_recovery_code_logs_in_once(client, login, employee) -> None:
    login(employee)
    _, codes = setup_2fa(client, employee)
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    first = client.post("/api/auth/2fa", json={"code": codes[0]})
    assert first.status_code == 200
    assert first.json()["user"]["recovery_codes_left"] == 9

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert client.post("/api/auth/2fa", json={"code": codes[0]}).status_code == 401


def test_reissue_requires_password(client, login, employee) -> None:
    login(employee)
    _, old = setup_2fa(client, employee)

    assert (
        client.post(
            "/api/auth/2fa/recovery-codes", json={"password": "не тот"}
        ).status_code
        == 401
    )
    new = client.post(
        "/api/auth/2fa/recovery-codes", json={"password": TEST_PASSWORD}
    ).json()["codes"]
    assert set(new).isdisjoint(old), "старые коды должны быть аннулированы"


def test_old_codes_stop_working_after_reissue(client, login, employee) -> None:
    login(employee)
    _, old = setup_2fa(client, employee)
    client.post("/api/auth/2fa/recovery-codes", json={"password": TEST_PASSWORD})
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert client.post("/api/auth/2fa", json={"code": old[0]}).status_code == 401


# --------------------------------------------------------------------------
# Обязательность по ролям
# --------------------------------------------------------------------------
def test_admin_must_set_up_2fa(client, admin) -> None:
    """Администратор без второго фактора в систему не попадает."""
    response = client.post(
        "/api/auth/login", json={"email": admin.email, "password": TEST_PASSWORD}
    )
    assert response.json()["status"] == "2fa_setup_required"
    assert client.get("/api/requests").status_code == 401


def test_finance_must_set_up_2fa(client, finance) -> None:
    response = client.post(
        "/api/auth/login", json={"email": finance.email, "password": TEST_PASSWORD}
    )
    assert response.json()["status"] == "2fa_setup_required"


def test_employee_may_skip_2fa(client, employee) -> None:
    response = client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert response.json()["status"] == "ok"


def test_forced_setup_completes_login(client, admin) -> None:
    """После обязательной настройки повторный вход не нужен."""
    client.post("/api/auth/login", json={"email": admin.email, "password": TEST_PASSWORD})
    setup = client.post("/api/auth/2fa/setup").json()
    client.post("/api/auth/2fa/confirm", json={"code": code_for(setup["secret"])})
    assert client.get("/api/requests").status_code == 200


def test_required_role_cannot_disable(client, admin) -> None:
    client.post("/api/auth/login", json={"email": admin.email, "password": TEST_PASSWORD})
    setup = client.post("/api/auth/2fa/setup").json()
    client.post("/api/auth/2fa/confirm", json={"code": code_for(setup["secret"])})

    response = client.post("/api/auth/2fa/disable", json={"password": TEST_PASSWORD})
    assert response.status_code == 409


def test_employee_can_disable_with_password(client, login, employee) -> None:
    login(employee)
    setup_2fa(client, employee)
    assert (
        client.post("/api/auth/2fa/disable", json={"password": "не тот"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/2fa/disable", json={"password": TEST_PASSWORD}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").json()["two_factor_enabled"] is False


# --------------------------------------------------------------------------
# Сброс администратором
# --------------------------------------------------------------------------
def test_admin_resets_lost_second_factor(client, login, employee, admin, session) -> None:
    login(employee)
    setup_2fa(client, employee)
    client.post("/api/auth/logout")

    # Администратору самому нужен второй фактор — проходим настройку
    client.post("/api/auth/login", json={"email": admin.email, "password": TEST_PASSWORD})
    setup = client.post("/api/auth/2fa/setup").json()
    client.post("/api/auth/2fa/confirm", json={"code": code_for(setup["secret"])})

    reset = client.post(f"/api/employees/{employee.id}/reset-2fa")
    assert reset.status_code == 200

    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert response.json()["status"] == "ok", "после сброса вход снова одношаговый"


def test_manager_cannot_reset_2fa(as_manager, employee) -> None:
    assert as_manager.post(f"/api/employees/{employee.id}/reset-2fa").status_code == 403


# --------------------------------------------------------------------------
# Защита от перебора
# --------------------------------------------------------------------------
def test_lockout_after_repeated_failures(client, employee, session) -> None:
    """Шестизначный код перебирается за часы, если попытки не ограничены."""
    from app.config import get_settings

    limit = get_settings().max_failed_logins
    for _ in range(limit):
        client.post(
            "/api/auth/login", json={"email": employee.email, "password": "не тот"}
        )

    response = client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert "заблокирован" in response.json()["detail"].lower()


def test_successful_login_resets_counter(client, employee, session) -> None:
    client.post("/api/auth/login", json={"email": employee.email, "password": "не тот"})
    client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    session.refresh(employee)
    assert employee.failed_logins == 0
