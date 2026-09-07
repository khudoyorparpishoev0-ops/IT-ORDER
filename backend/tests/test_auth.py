"""Вход, сессия, пароли."""

from __future__ import annotations

import pytest

from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    token_subject,
    validate_password_strength,
    verify_password,
)
from tests.conftest import TEST_PASSWORD


def test_password_hash_is_not_reversible() -> None:
    h = hash_password("длинная секретная фраза")
    assert "длинная" not in h
    assert h.startswith("$argon2")


def test_same_password_gives_different_hashes() -> None:
    """Соль у каждого хэша своя: одинаковые пароли не видно по базе."""
    assert hash_password("одна и та же фраза") != hash_password("одна и та же фраза")


def test_verify_password() -> None:
    h = hash_password("правильная фраза")
    assert verify_password("правильная фраза", h)
    assert not verify_password("неправильная фраза", h)


def test_broken_hash_does_not_raise() -> None:
    """Битая запись в базе не должна ронять вход — это просто «не совпало»."""
    assert not verify_password("что угодно", "не-хэш-вовсе")
    assert needs_rehash("не-хэш-вовсе")


@pytest.mark.parametrize("bad", ["короткий", " пароль_с_пробелом ", ""])
def test_weak_passwords_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_password_strength(bad)


def test_long_passphrase_accepted() -> None:
    validate_password_strength("длинная запоминающаяся фраза")


def test_token_roundtrip() -> None:
    token = create_token(42, role="manager")
    assert token_subject(token) == 42
    assert decode_token(token)["role"] == "manager"


def test_tampered_token_rejected() -> None:
    token = create_token(42, role="employee")
    # Меняем один символ подписи — токен должен перестать проходить
    broken = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(TokenError):
        token_subject(broken)


def test_garbage_token_rejected() -> None:
    with pytest.raises(TokenError):
        token_subject("совсем не токен")


def test_login_sets_httponly_cookie(client, manager) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": manager.email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "httponly" in cookie.lower(), "токен должен быть недоступен скриптам"
    assert "samesite=lax" in cookie.lower(), "нужна защита от межсайтовых запросов"


def test_login_updates_last_login(client, manager, session) -> None:
    assert manager.last_login_at is None
    client.post(
        "/api/auth/login", json={"email": manager.email, "password": TEST_PASSWORD}
    )
    session.refresh(manager)
    assert manager.last_login_at is not None


def test_wrong_password_is_401(client, manager) -> None:
    response = client.post(
        "/api/auth/login", json={"email": manager.email, "password": "не тот пароль"}
    )
    assert response.status_code == 401


def test_unknown_email_gives_same_message(client, manager) -> None:
    """Ответ не должен выдавать, заведена ли такая почта."""
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@it-hona.tj", "password": "любой пароль"},
    )
    wrong = client.post(
        "/api/auth/login", json={"email": manager.email, "password": "не тот пароль"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_employee_without_password_cannot_sign_in(client, session) -> None:
    """Сотрудник заведён для отчётности, но входа у него нет."""
    from app.db.models import Employee

    person = Employee(full_name="Без доступа", email="no.access@it-hona.tj")
    session.add(person)
    session.flush()

    response = client.post(
        "/api/auth/login",
        json={"email": person.email, "password": "любой пароль"},
    )
    assert response.status_code == 401


def test_inactive_employee_cannot_sign_in(client, session, manager) -> None:
    manager.active = False
    session.flush()
    response = client.post(
        "/api/auth/login", json={"email": manager.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


def test_me_returns_permissions(as_manager, manager) -> None:
    body = as_manager.get("/api/auth/me").json()
    assert body["id"] == manager.id
    assert body["role"] == "manager"
    assert "decide_request" in body["permissions"]
    assert "pay_request" not in body["permissions"]


def test_logout_clears_session(as_manager) -> None:
    assert as_manager.get("/api/auth/me").status_code == 200
    assert as_manager.post("/api/auth/logout").status_code == 204
    assert as_manager.get("/api/auth/me").status_code == 401


def test_change_own_password(client, login, manager) -> None:
    login(manager)
    response = client.post(
        "/api/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "новая длинная фраза"},
    )
    assert response.status_code == 200

    client.post("/api/auth/logout")
    old = client.post(
        "/api/auth/login", json={"email": manager.email, "password": TEST_PASSWORD}
    )
    new = client.post(
        "/api/auth/login",
        json={"email": manager.email, "password": "новая длинная фраза"},
    )
    assert old.status_code == 401
    assert new.status_code == 200


def test_change_password_requires_current(as_manager) -> None:
    response = as_manager.post(
        "/api/auth/password",
        json={"current_password": "не тот", "new_password": "новая длинная фраза"},
    )
    assert response.status_code == 401


def test_new_password_must_be_strong(as_manager) -> None:
    response = as_manager.post(
        "/api/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "коротко"},
    )
    assert response.status_code == 422


def test_admin_sets_password_for_employee(client, login, admin, session) -> None:
    """Так заводят доступ новому сотруднику и восстанавливают забытый пароль."""
    from app.db.models import Employee

    person = Employee(full_name="Новый сотрудник", email="new@it-hona.tj")
    session.add(person)
    session.flush()

    login(admin)
    response = client.put(
        f"/api/employees/{person.id}/password", json={"password": "выданная длинная фраза"}
    )
    assert response.status_code == 200

    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login",
            json={"email": person.email, "password": "выданная длинная фраза"},
        ).status_code
        == 200
    )


def test_manager_cannot_set_passwords(as_manager, employee) -> None:
    response = as_manager.put(
        f"/api/employees/{employee.id}/password", json={"password": "чужая длинная фраза"}
    )
    assert response.status_code == 403
