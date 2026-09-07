"""Фикстуры тестов. Работают на настоящей PostgreSQL: SQLite не воспроизводит
поведение NUMERIC, timestamptz и ограничений, ради которых тесты и написаны."""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from functools import lru_cache

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("POSTGRES_DB", "hona_core_test")
os.environ.setdefault("APP_ENV", "development")
# Почта в тестах «настроена»: отправку перехватывает фикстура mailbox,
# в сеть тесты не ходят. Без этих значений эндпоинты справедливо
# отказываются отправлять письма.
# Домен почты в тестах фиксирован и не зависит от домена заказчика:
# смена ALLOWED_EMAIL_DOMAINS в .env не должна ломать прогон.
os.environ.setdefault("ALLOWED_EMAIL_DOMAINS", "it-hona.tj")
os.environ.setdefault("SMTP_USER", "core@it-hona.tj")
os.environ.setdefault("SMTP_PASSWORD", "тестовый-пароль-приложения")
os.environ.setdefault("PUBLIC_BASE_URL", "https://order.it-hona.tj")
# TestClient ходит по http://testserver, а cookie с secure=true браузерный
# cookiejar по http не сохраняет — вход в тестах разваливался бы на втором
# шаге. Значение задаётся здесь, чтобы прогон не зависел от .env на машине.
os.environ.setdefault("COOKIE_SECURE", "false")

from app.api.deps import get_db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.models import Base, Employee, EmployeeRole, MonthlyBudget, Project  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(get_settings().database_url, future=True)
    # Схему в тестах создаём напрямую: миграции проверяются отдельно,
    # прогоном alembic upgrade head в CI.
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    """Чистая база на каждый тест: между тестами таблицы обрезаются."""
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        # RESTART IDENTITY сбрасывает только счётчики колонок таблиц.
        # Номера заявок живут в отдельной последовательности — её вручную.
        conn.execute(text("ALTER SEQUENCE request_number_seq RESTART WITH 1"))
    db = factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def client(session) -> Iterator[TestClient]:
    """Клиент API поверх той же сессии, что видит тест."""

    def override() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
        for key in [k for k in _TOTP_SECRETS if k[0] == id(c)]:
            _TOTP_SECRETS.pop(key, None)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_outgoing_mail():
    """Ни один тест не должен ходить в сеть.

    Без этого тесты, задевающие уведомления, пытались достучаться до
    настоящего SMTP и ждали таймаута — прогон растягивался на минуты.
    Фикстуры mailbox и broken_mail подменяют транспорт своим.
    """
    from app.core import mail

    class Silent:
        def send(self, message) -> None:
            pass

    mail.set_transport(Silent())
    yield
    mail.set_transport(None)


@pytest.fixture
def mailbox(monkeypatch):
    """Перехватывает отправку почты. В сеть тесты не ходят."""
    from email.message import EmailMessage

    from app.core import mail

    sent: list[EmailMessage] = []

    class Collecting:
        def send(self, message: EmailMessage) -> None:
            sent.append(message)

    mail.set_transport(Collecting())
    # Фоновые задачи FastAPI выполняются в том же процессе, поэтому
    # письма попадают сюда же.
    yield sent
    mail.set_transport(None)


@pytest.fixture
def broken_mail():
    """Почтовый сервер недоступен: проверяем, что это не ломает действия."""
    from app.core import mail

    class Failing:
        def send(self, message) -> None:
            raise mail.MailError("SMTP недоступен")

    mail.set_transport(Failing())
    yield
    mail.set_transport(None)


@pytest.fixture
def project(session) -> Project:
    p = Project(name="Вилла Колхозная")
    session.add(p)
    session.flush()
    return p


#: Пароль всех тестовых учётных записей.
TEST_PASSWORD = "тестовый-пароль-подлиннее"


def make_employee(session, **kwargs) -> Employee:
    """Сотрудник с возможностью входа. Пароль хэшируется один раз на модуль:
    Argon2 намеренно медленный, и хэширование в каждом тесте съедает прогон."""
    defaults = dict(
        position="Сотрудник",
        role=EmployeeRole.EMPLOYEE,
        password_hash=_password_hash(),
    )
    person = Employee(**{**defaults, **kwargs})
    session.add(person)
    session.flush()
    return person


@lru_cache(maxsize=1)
def _password_hash() -> str:
    from app.core.security import hash_password

    return hash_password(TEST_PASSWORD)


@pytest.fixture
def employee(session) -> Employee:
    return make_employee(
        session,
        full_name="Иван Петров",
        position="Мастер-отделочник",
        email="i.petrov@it-hona.tj",
        role=EmployeeRole.EMPLOYEE,
        monthly_limit=Decimal("5000.00"),
    )


@pytest.fixture
def manager(session) -> Employee:
    return make_employee(
        session,
        full_name="Артём Ковалёв",
        position="Руководитель отдела",
        email="a.kovalev@it-hona.tj",
        role=EmployeeRole.MANAGER,
    )


@pytest.fixture
def finance(session) -> Employee:
    return make_employee(
        session,
        full_name="Нигина Рахимова",
        position="Бухгалтер",
        email="n.rahimova@it-hona.tj",
        role=EmployeeRole.FINANCE,
    )


@pytest.fixture
def admin(session) -> Employee:
    return make_employee(
        session,
        full_name="Администратор",
        position="Администратор системы",
        email="admin@it-hona.tj",
        role=EmployeeRole.ADMIN,
    )


@pytest.fixture
def login(client, session):
    """Вход в клиента под указанным сотрудником. Cookie остаётся в клиенте.

    Ролям с обязательным вторым фактором фикстура проходит настройку сама:
    тесты прав и выгрузок проверяют не сценарий входа, и загромождать их
    вознёй с кодами незачем. Сам двухфакторный вход проверяется отдельно
    в tests/test_two_factor.py.
    """

    def _login(person: Employee) -> None:
        # Выходим перед сменой пользователя: два сеанса в одном клиенте
        # смешиваются так же, как смешались бы в одном браузере.
        client.post("/api/auth/logout")
        response = client.post(
            "/api/auth/login",
            json={"email": person.email, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, response.text
        status = response.json()["status"]

        if status == "2fa_setup_required":
            _pass_2fa_setup(client, person)
        elif status == "2fa_required":
            _pass_2fa_code(client, session, person)

    return _login


def _pass_2fa_setup(client, person: Employee) -> None:
    """Проходит обязательную настройку второго фактора."""
    import pyotp

    setup = client.post("/api/auth/2fa/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    # Ключ — пара «клиент + сотрудник»: в одном тесте под одним клиентом
    # входят несколько человек, и общий ключ затирался чужим секретом.
    _TOTP_SECRETS[(id(client), person.id)] = secret

    confirmed = client.post(
        "/api/auth/2fa/confirm", json={"code": pyotp.TOTP(secret).now()}
    )
    assert confirmed.status_code == 200, confirmed.text


def _pass_2fa_code(client, session, person: Employee) -> None:
    """Вводит код для уже настроенного второго фактора."""
    import pyotp

    secret = _TOTP_SECRETS.get((id(client), person.id))
    assert secret, f"неизвестен секрет TOTP для {person.email}"
    # Защита от повторного применения кода настоящая и нужная, но в тестах
    # один и тот же человек входит по нескольку раз за секунду. Снимаем
    # отметку о последнем использованном шаге — это подготовка стенда,
    # проверяется защита отдельно, в tests/test_two_factor.py.
    person.totp_last_step = None
    session.flush()
    session.commit()

    response = client.post("/api/auth/2fa", json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 200, response.text


#: Секреты TOTP, выданные в текущем тесте: нужны, чтобы повторно войти
#: тем же клиентом. Ключ — «клиент + сотрудник». Живут в пределах теста.
_TOTP_SECRETS: dict[tuple[int, int], str] = {}


@pytest.fixture
def as_manager(client, manager, login):
    """Клиент, вошедший руководителем — самая частая роль в тестах API."""
    login(manager)
    return client


@pytest.fixture
def budget(session) -> MonthlyBudget:
    from app.services.reports import current_period

    year, month = current_period()
    b = MonthlyBudget(year=year, month=month, amount=Decimal("156000.00"))
    session.add(b)
    session.flush()
    return b
