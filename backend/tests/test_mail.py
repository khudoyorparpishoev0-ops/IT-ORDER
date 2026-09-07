"""Почта: отправка, восстановление пароля, уведомления."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.mail import Letter, MailError, build_message, send, send_quietly
from app.core.security import (
    TokenError,
    create_password_reset_token,
    password_fingerprint,
    read_password_reset_token,
)
from app.services import mail_templates as templates
from tests.conftest import TEST_PASSWORD

NEW_PASSWORD = "новая длинная фраза"


# --------------------------------------------------------------------------
# Сборка письма
# --------------------------------------------------------------------------
def test_letter_has_text_part() -> None:
    """Письмо без текстовой части хуже проходит спам-фильтры."""
    message = build_message(
        Letter(to="a@it-hona.tj", subject="Тема", text="Текст", html="<p>Текст</p>")
    )
    assert message.is_multipart()
    types = {part.get_content_type() for part in message.walk()}
    assert "text/plain" in types
    assert "text/html" in types


def test_cyrillic_subject_and_body(mailbox) -> None:
    send(Letter(to="i.petrov@it-hona.tj", subject="Заявка РЗ-0001", text="Здравствуйте"))
    sent = mailbox[0]
    assert sent["Subject"] == "Заявка РЗ-0001"
    assert "Здравствуйте" in sent.get_body(("plain",)).get_content()


def test_send_quietly_swallows_failure(broken_mail) -> None:
    """Неудача письма не должна отменять уже совершённое действие."""
    send_quietly(Letter(to="a@it-hona.tj", subject="Тема", text="Текст"))


def test_send_raises_for_caller_to_handle(broken_mail) -> None:
    with pytest.raises(MailError):
        send(Letter(to="a@it-hona.tj", subject="Тема", text="Текст"))


# --------------------------------------------------------------------------
# Токен восстановления
# --------------------------------------------------------------------------
def test_reset_token_roundtrip() -> None:
    token = create_password_reset_token(7, password_hash="хэш")
    employee_id, fingerprint = read_password_reset_token(token)
    assert employee_id == 7
    assert fingerprint == password_fingerprint("хэш")


def test_session_token_is_not_a_reset_link() -> None:
    from app.core.security import create_token

    with pytest.raises(TokenError):
        read_password_reset_token(create_token(7, role="admin"))


# --------------------------------------------------------------------------
# Восстановление пароля
# --------------------------------------------------------------------------
def test_reset_request_sends_letter(client, employee, mailbox) -> None:
    response = client.post(
        "/api/auth/password-reset/request", json={"email": employee.email}
    )
    assert response.status_code == 204
    assert len(mailbox) == 1
    assert mailbox[0]["To"] == employee.email
    assert "reset-password?token=" in mailbox[0].get_body(("plain",)).get_content()


def test_reset_request_hides_unknown_address(client, mailbox) -> None:
    """Ответ одинаков, иначе перебором выясняется, кто заведён."""
    known = client.post(
        "/api/auth/password-reset/request", json={"email": "nobody@it-hona.tj"}
    )
    assert known.status_code == 204
    assert mailbox == []


def test_reset_request_ignores_personal_domain(client, mailbox) -> None:
    response = client.post(
        "/api/auth/password-reset/request", json={"email": "someone@gmail.com"}
    )
    assert response.status_code == 204
    assert mailbox == []


def test_reset_applies_new_password(client, employee, mailbox) -> None:
    client.post("/api/auth/password-reset/request", json={"email": employee.email})
    token = _token_from(mailbox[0])

    applied = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert applied.status_code == 200

    assert (
        client.post(
            "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": employee.email, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


def test_reset_link_works_once(client, employee, mailbox) -> None:
    """Отпечаток пароля в токене гасит ссылку, как только пароль сменился."""
    client.post("/api/auth/password-reset/request", json={"email": employee.email})
    token = _token_from(mailbox[0])
    client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    second = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "new_password": "ещё одна длинная фраза"},
    )
    assert second.status_code == 401


def test_reset_rejects_garbage_token(client) -> None:
    response = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "не токен", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 401


def test_reset_enforces_password_strength(client, employee, mailbox) -> None:
    client.post("/api/auth/password-reset/request", json={"email": employee.email})
    response = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": _token_from(mailbox[0]), "new_password": "коротко"},
    )
    assert response.status_code == 422


def test_reset_does_not_bypass_second_factor(client, login, employee, mailbox) -> None:
    """Доступ к почте не должен заменять второй фактор."""
    import pyotp

    login(employee)
    setup = client.post("/api/auth/2fa/setup").json()
    client.post("/api/auth/2fa/confirm", json={"code": pyotp.TOTP(setup["secret"]).now()})
    client.post("/api/auth/logout")
    mailbox.clear()

    client.post("/api/auth/password-reset/request", json={"email": employee.email})
    client.post(
        "/api/auth/password-reset/confirm",
        json={"token": _token_from(mailbox[0]), "new_password": NEW_PASSWORD},
    )
    # Сессию смена пароля не выдаёт
    assert client.get("/api/auth/me").status_code == 401
    # А вход по новому паролю всё равно требует код
    result = client.post(
        "/api/auth/login", json={"email": employee.email, "password": NEW_PASSWORD}
    )
    assert result.json()["status"] == "2fa_required"


def test_reset_unlocks_blocked_account(client, employee, session, mailbox) -> None:
    """Подтверждённый доступ к почте снимает блокировку от перебора."""
    from app.config import get_settings

    for _ in range(get_settings().max_failed_logins):
        client.post(
            "/api/auth/login", json={"email": employee.email, "password": "не тот"}
        )
    mailbox.clear()

    client.post("/api/auth/password-reset/request", json={"email": employee.email})
    client.post(
        "/api/auth/password-reset/confirm",
        json={"token": _token_from(mailbox[0]), "new_password": NEW_PASSWORD},
    )
    result = client.post(
        "/api/auth/login", json={"email": employee.email, "password": NEW_PASSWORD}
    )
    assert result.status_code == 200


def _token_from(message) -> str:
    body = message.get_body(("plain",)).get_content()
    for word in body.split():
        if "token=" in word:
            return word.split("token=", 1)[1].strip()
    raise AssertionError("в письме нет ссылки с токеном")


# --------------------------------------------------------------------------
# Уведомления
# --------------------------------------------------------------------------
def test_new_request_notifies_approvers(
    client, login, employee, manager, project, mailbox
) -> None:
    login(employee)
    mailbox.clear()
    client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Материалы", "quantity": 1, "price": "2000.00"}],
        },
    )
    recipients = {m["To"] for m in mailbox}
    assert manager.email in recipients
    assert employee.email not in recipients, "автору о своей заявке не пишем"


def test_auto_approved_request_sends_nothing(
    client, login, employee, manager, project, mailbox
) -> None:
    """Заявка ниже порога закрывается сама — решать нечего."""
    login(employee)
    mailbox.clear()
    client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Обед", "quantity": 1, "price": "30.00"}],
        },
    )
    assert mailbox == []


def test_notification_can_be_turned_off(
    client, login, employee, manager, project, session, mailbox
) -> None:
    manager.notify_new_requests = False
    session.flush()

    login(employee)
    mailbox.clear()
    client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Материалы", "quantity": 1, "price": "2000.00"}],
        },
    )
    assert manager.email not in {m["To"] for m in mailbox}


def test_finance_is_not_notified_about_approvals(
    client, login, employee, finance, project, session, mailbox
) -> None:
    """Письмо идёт только тем, кто вправе решать."""
    login(employee)
    mailbox.clear()
    client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Материалы", "quantity": 1, "price": "2000.00"}],
        },
    )
    assert finance.email not in {m["To"] for m in mailbox}


def test_toggle_notifications_endpoint(client, login, employee) -> None:
    login(employee)
    body = client.patch(
        "/api/auth/notifications", json={"new_requests": False}
    ).json()
    assert body["notifications"]["new_requests"] is False
    assert body["notifications"]["stale_requests"] is True


def test_broken_mail_does_not_break_request(
    client, login, employee, manager, project, broken_mail
) -> None:
    """Недоступный SMTP не должен мешать подать заявку."""
    login(employee)
    response = client.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Материалы", "quantity": 1, "price": "2000.00"}],
        },
    )
    assert response.status_code == 201


# --------------------------------------------------------------------------
# Проверочное письмо
# --------------------------------------------------------------------------
def test_admin_sends_test_mail(client, login, admin, mailbox) -> None:
    login(admin)
    assert client.post("/api/mail/test").status_code == 204
    assert mailbox[-1]["To"] == admin.email


def test_manager_cannot_send_test_mail(as_manager) -> None:
    assert as_manager.post("/api/mail/test").status_code == 403


def test_test_mail_reports_smtp_error(client, login, admin, broken_mail) -> None:
    """Администратор должен увидеть причину, а не гадать."""
    login(admin)
    response = client.post("/api/mail/test")
    assert response.status_code == 422
    assert "SMTP" in response.json()["detail"] or "письмо" in response.json()["detail"]


# --------------------------------------------------------------------------
# Шаблоны
# --------------------------------------------------------------------------
def test_templates_render_money_in_ru_format() -> None:
    from app.core.money import money

    letter = templates.request_awaiting_approval(
        approver_name="Артём",
        employee_name="Иван Петров",
        number="РЗ-0001",
        project="Вилла Колхозная",
        amount=Decimal("1850"),
        url="https://core.it-hona.tj/approvals",
    )
    # Разделитель разрядов — неразрывный пробел, чтобы число не рвалось
    # переносом строки; сравниваем с money(), а не с литералом.
    assert money(Decimal("1850")) in letter.text
    assert "РЗ-0001" in letter.subject
