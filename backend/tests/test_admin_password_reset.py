"""Административный сброс пароля: подтверждение, сеансы, обязательная смена.

Сброс чужого пароля — самое опасное, что умеет администратор: он даёт
вход в любую учётную запись, включая бухгалтерию. Поэтому здесь проверяется
не «работает ли кнопка», а каждый способ ею злоупотребить.
"""

from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.db.models import AuditLog, Employee
from tests.conftest import TEST_PASSWORD

NEW = "выданный-администратором-пароль"


def reset(client, employee, code, password=NEW):
    return client.put(
        f"/api/employees/{employee.id}/password",
        json={"password": password, "totp_code": code},
    )


def audit(session, action):
    return list(
        session.scalars(select(AuditLog).where(AuditLog.action == action))
    )


# --- Кому вообще можно -------------------------------------------------------------


def test_employee_cannot_reset_anyones_password(client, login, employee, manager) -> None:
    login(employee)
    answer = reset(client, manager, "123456")
    assert answer.status_code == 403


def test_manager_cannot_reset_password(client, login, manager, employee) -> None:
    """Руководитель ведёт заявки, а не доступы. Права `manage_reference` у него нет."""
    login(manager)
    assert reset(client, employee, "123456").status_code == 403


def test_reset_requires_login(client, employee) -> None:
    assert reset(client, employee, "123456").status_code == 401


# --- Подтверждение вторым фактором -------------------------------------------------


def test_wrong_code_does_not_change_the_password(
    client, login, session, admin, employee
) -> None:
    login(admin)
    before = employee.password_hash

    answer = reset(client, employee, "000000")

    assert answer.status_code == 422
    assert "код" in answer.json()["detail"].lower()
    session.refresh(employee)
    assert employee.password_hash == before, "пароль изменился при неверном коде"


def test_failed_attempt_is_recorded(client, login, session, admin, employee) -> None:
    """Попытка сбросить чужой пароль — то, о чём владелец должен узнать,
    даже если она не удалась."""
    login(admin)
    reset(client, employee, "000000")

    записи = audit(session, "admin_password_reset_failed")
    assert записи, "неудачная попытка не попала в журнал"
    последняя = записи[-1]
    assert последняя.username == admin.full_name
    assert employee.full_name in (последняя.details or "")
    assert последняя.ip, "адрес не записан"


def test_correct_code_resets_the_password(
    client, login, session, admin, employee, totp_code
) -> None:
    login(admin)
    before = employee.password_hash

    answer = reset(client, employee, totp_code(admin))

    assert answer.status_code == 200, answer.text
    session.refresh(employee)
    assert employee.password_hash != before


def test_reused_code_does_not_pass_twice(
    client, login, session, admin, employee, manager
) -> None:
    """Подсмотренный код не срабатывает второй раз в том же окне."""
    import pyotp

    from tests.conftest import _TOTP_SECRETS

    login(admin)
    secret = _TOTP_SECRETS[(id(client), admin.id)]
    admin.totp_last_step = None
    session.commit()

    код = pyotp.TOTP(secret).now()
    assert reset(client, employee, код).status_code == 200
    # Тот же код, другая цель — обход не проходит.
    assert reset(client, manager, код).status_code == 422


def test_brute_force_is_limited(client, login, session, admin, employee) -> None:
    """Шестизначный код перебирается за миллион попыток."""
    login(admin)
    limit = get_settings().max_failed_logins

    for _ in range(limit):
        reset(client, employee, "000000")

    session.refresh(admin)
    assert admin.locked_until is not None


def test_admin_without_2fa_is_refused(
    client, login, session, admin, employee, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "require_2fa_roles", "")
    login(admin)
    admin.totp_enabled = False
    admin.totp_secret = None
    session.commit()

    answer = reset(client, employee, "000000")
    assert answer.status_code == 422
    assert "двухфакторн" in answer.json()["detail"].lower()


# --- Кого можно сбрасывать ---------------------------------------------------------


def test_disabled_employee_is_not_reset(
    client, login, session, admin, employee, totp_code
) -> None:
    """Сброс уволенному только открывает ему дверь обратно."""
    employee.active = False
    session.commit()
    login(admin)

    answer = reset(client, employee, totp_code(admin))
    assert answer.status_code == 422
    assert "не работает" in answer.json()["detail"].lower()


def test_missing_employee_is_404(client, login, admin, totp_code) -> None:
    login(admin)
    answer = client.put(
        "/api/employees/999999/password",
        json={"password": NEW, "totp_code": totp_code(admin)},
    )
    assert answer.status_code == 404


def test_another_admin_is_reset_by_the_same_rules(
    client, login, session, admin, totp_code
) -> None:
    """Второй администратор — не исключение и не лазейка."""
    from app.db.models import EmployeeRole
    from tests.conftest import make_employee

    другой = make_employee(
        session,
        full_name="Второй Администратор",
        position="Администратор",
        email="admin2@it-hona.tj",
        role=EmployeeRole.ADMIN,
    )
    session.commit()
    login(admin)

    assert reset(client, другой, "000000").status_code == 422
    assert reset(client, другой, totp_code(admin)).status_code == 200
    session.refresh(другой)
    # Роль сбросом не меняется: повысить себя через этот эндпоинт нельзя.
    assert другой.role is EmployeeRole.ADMIN


# --- Что происходит после сброса ---------------------------------------------------


def test_old_password_stops_working(
    client, login, session, admin, employee, totp_code
) -> None:
    login(admin)
    assert reset(client, employee, totp_code(admin)).status_code == 200
    client.post("/api/auth/logout")

    старый = client.post(
        "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
    )
    assert старый.status_code == 401

    новый = client.post(
        "/api/auth/login", json={"email": employee.email, "password": NEW}
    )
    assert новый.status_code == 200, новый.text


def test_open_sessions_are_terminated(client, login, session, admin, employee, totp_code) -> None:
    """Cookie, оставшаяся на чужом устройстве, дальше не работает.

    Проверяется двумя клиентами: у сотрудника своя открытая сессия,
    администратор в это время сбрасывает ему пароль.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as сотрудник:
        вход = сотрудник.post(
            "/api/auth/login", json={"email": employee.email, "password": TEST_PASSWORD}
        )
        assert вход.status_code == 200, вход.text
        assert сотрудник.get("/api/auth/me").status_code == 200

        login(admin)
        assert reset(client, employee, totp_code(admin)).status_code == 200

        # Та же cookie, тот же клиент — и уже не пускают.
        after = сотрудник.get("/api/auth/me")
        assert after.status_code == 401, "старая сессия пережила сброс пароля"


def test_temporary_password_must_be_changed(
    client, login, session, admin, employee, totp_code
) -> None:
    login(admin)
    assert reset(client, employee, totp_code(admin)).status_code == 200
    session.refresh(employee)
    assert employee.must_change_password is True

    client.post("/api/auth/logout")
    вход = client.post(
        "/api/auth/login", json={"email": employee.email, "password": NEW}
    )
    assert вход.status_code == 200
    assert client.get("/api/auth/me").json()["must_change_password"] is True

    # До смены пароля работа закрыта.
    закрыто = client.get("/api/requests")
    assert закрыто.status_code == 403
    assert "временный пароль" in закрыто.json()["detail"].lower()

    свой = client.post(
        "/api/auth/password",
        json={"current_password": NEW, "new_password": "мой-собственный-пароль-1"},
    )
    assert свой.status_code == 200, свой.text
    assert свой.json()["must_change_password"] is False

    # Смена пароля погасила и эту сессию — входим заново и работаем.
    client.post(
        "/api/auth/login",
        json={"email": employee.email, "password": "мой-собственный-пароль-1"},
    )
    assert client.get("/api/requests").status_code == 200


def test_self_service_reset_is_not_temporary(client, session, employee, mailbox) -> None:
    """Пароль по ссылке из письма человек выбрал сам — сменять его снова
    незачем."""
    from app.services import auth as svc

    client.post("/api/auth/password-reset/request", json={"email": employee.email})
    токен = svc.create_password_reset_token(
        employee.id, password_hash=employee.password_hash
    )
    answer = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": токен, "new_password": "пароль-из-письма-длинный"},
    )
    assert answer.status_code == 200, answer.text
    session.refresh(employee)
    assert employee.must_change_password is False


# --- Журнал ------------------------------------------------------------------------


def test_audit_has_both_names_and_no_secrets(
    client, login, session, admin, employee, totp_code
) -> None:
    login(admin)
    код = totp_code(admin)
    assert reset(client, employee, код).status_code == 200

    записи = audit(session, "admin_password_reset")
    assert записи, "успешный сброс не попал в журнал"
    запись = записи[-1]

    assert запись.username == admin.full_name
    assert запись.employee_id == employee.id
    assert employee.full_name in (запись.details or "")
    assert запись.ip, "адрес не записан"

    # Ни пароля, ни кода, ни секрета — ни в одной записи журнала.
    всё = " ".join(
        f"{r.details or ''} {r.username or ''} {r.entity_id}"
        for r in session.scalars(select(AuditLog))
    )
    for секрет in (NEW, код, admin.totp_secret or "нет-секрета"):
        assert секрет not in всё


def test_totp_secret_never_leaves_the_server(client, login, admin, employee) -> None:
    """Секрет 2FA не возвращается ни одним ответом API."""
    login(admin)
    for path in ("/api/auth/me", "/api/employees", "/api/employees/access"):
        тело = client.get(path).text
        assert (admin.totp_secret or "нет") not in тело
        assert "totp_secret" not in тело


def test_password_never_appears_in_any_response(
    client, login, admin, employee, totp_code
) -> None:
    login(admin)
    ответ = reset(client, employee, totp_code(admin))
    assert NEW not in ответ.text
    assert "password_hash" not in ответ.text


def test_seeded_employees_are_not_locked_out(session) -> None:
    """Существующие сотрудники не заперты задним числом.

    Их пароли выданы до появления правила, и требовать смены у всей
    компании разом — не исправление, а остановка работы.
    """
    для_всех = session.scalars(select(Employee)).all()
    assert not [p for p in для_всех if p.must_change_password]
