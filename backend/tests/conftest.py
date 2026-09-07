"""Фикстуры тестов. Работают на настоящей PostgreSQL: SQLite не воспроизводит
поведение NUMERIC, timestamptz и ограничений, ради которых тесты и написаны."""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal

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


@pytest.fixture
def employee(session) -> Employee:
    e = Employee(
        full_name="Иван Петров",
        position="Мастер-отделочник",
        email="i.petrov@it-hona.tj",
        role=EmployeeRole.EMPLOYEE,
        monthly_limit=Decimal("5000.00"),
    )
    session.add(e)
    session.flush()
    return e


@pytest.fixture
def budget(session) -> MonthlyBudget:
    from app.services.reports import current_period

    year, month = current_period()
    b = MonthlyBudget(year=year, month=month, amount=Decimal("156000.00"))
    session.add(b)
    session.flush()
    return b
