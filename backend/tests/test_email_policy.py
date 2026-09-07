"""Корпоративная почта как условие доступа."""

from __future__ import annotations

import pytest

from app.core.email_policy import (
    EmailPolicyError,
    domain_of,
    ensure_corporate,
    is_corporate,
    normalize,
)
from app.core.errors import ValidationError
from app.db.models import Employee, EmployeeRole
from app.schemas.reference import EmployeeCreate, EmployeeUpdate
from app.services import reference as svc
from tests.conftest import TEST_PASSWORD


def test_normalize_lowercases_and_trims() -> None:
    assert normalize("  I.Petrov@IT-HONA.TJ ") == "i.petrov@it-hona.tj"


def test_domain_of() -> None:
    assert domain_of("A.B@IT-HONA.TJ") == "it-hona.tj"


@pytest.mark.parametrize(
    "email",
    ["i.petrov@it-hona.tj", "I.PETROV@IT-HONA.TJ", " a.b@it-hona.tj "],
)
def test_corporate_accepted(email: str) -> None:
    assert is_corporate(email)
    assert ensure_corporate(email).islower()


@pytest.mark.parametrize(
    "email",
    [
        "petrov@gmail.com",
        "petrov@mail.ru",
        "petrov@it-hona.tj.evil.com",
        "petrov@sub.it-hona.tj",
    ],
)
def test_personal_and_lookalike_rejected(email: str) -> None:
    """Похожий домен — не тот же самый: сравнение точное, не по вхождению."""
    assert not is_corporate(email)
    with pytest.raises(EmailPolicyError):
        ensure_corporate(email)


def test_not_an_email_rejected() -> None:
    with pytest.raises(EmailPolicyError):
        ensure_corporate("просто строка")


def test_create_employee_rejects_personal_email(session) -> None:
    with pytest.raises(ValidationError):
        svc.create_employee(
            session, EmployeeCreate(full_name="Чужой", email="someone@gmail.com")
        )


def test_create_employee_normalizes_email(session) -> None:
    employee = svc.create_employee(
        session, EmployeeCreate(full_name="Новый", email="Novyi@IT-HONA.TJ")
    )
    assert employee.email == "novyi@it-hona.tj"


def test_duplicate_email_in_other_case_is_conflict(session, employee) -> None:
    from app.core.errors import ConflictError

    with pytest.raises(ConflictError):
        svc.create_employee(
            session,
            EmployeeCreate(full_name="Дубль", email=employee.email.upper()),
        )


def test_update_employee_rejects_personal_email(session, employee) -> None:
    with pytest.raises(ValidationError):
        svc.update_employee(
            session, employee.id, EmployeeUpdate(email="someone@yandex.ru")
        )


def test_employee_without_email_is_allowed(session) -> None:
    """Сотрудник может фигурировать в заявках, не имея доступа в систему."""
    person = svc.create_employee(session, EmployeeCreate(full_name="Без почты"))
    assert person.email is None
    assert not person.can_sign_in


def test_login_blocked_if_domain_no_longer_corporate(
    client, session, monkeypatch
) -> None:
    """Политику могли ужесточить после того, как сотрудник был заведён."""
    from app.core.security import hash_password

    person = Employee(
        full_name="Старый адрес",
        email="old@legacy.tj",
        role=EmployeeRole.EMPLOYEE,
        password_hash=hash_password(TEST_PASSWORD),
    )
    session.add(person)
    session.flush()

    response = client.post(
        "/api/auth/login", json={"email": person.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert "корпоративн" in response.json()["detail"].lower()


def test_policy_endpoint_is_public(client) -> None:
    """Экран входа показывает подсказку до авторизации."""
    body = client.get("/api/auth/policy").json()
    assert body["email_domains"] == ["it-hona.tj"]
    assert body["domains_hint"] == "@it-hona.tj"
