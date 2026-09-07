"""Подключение к базе. Одна фабрика сессий на процесс."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        # pool_pre_ping спасает от «server closed the connection»
        # после простоя: соединение проверяется перед выдачей.
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        echo=False,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def session_scope() -> Iterator[Session]:
    """Сессия для фоновых задач и скриптов. Роллбэк при исключении."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
