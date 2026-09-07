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
    app.dependency_overrides.clear()


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
def login(client):
    """Вход в клиента под указанным сотрудником. Cookie остаётся в клиенте."""

    def _login(person: Employee) -> None:
        response = client.post(
            "/api/auth/login",
            json={"email": person.email, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, response.text

    return _login


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
