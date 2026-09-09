"""Окружение Alembic. URL и метаданные берутся из приложения."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.config import get_settings
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return get_settings().database_url


#: Индексы, которых нет в модели намеренно: они ускоряют работу, но
#: зависят от расширений PostgreSQL, а те могут быть недоступны по
#: правам. Их ставит миграция, если база даёт, и приложение обязано
#: работать без них. Сравнивать их с моделью нечего — она о них не знает.
OPTIONAL_INDEXES = {"ix_lines_normalized_trgm"}


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    return not (type_ == "index" and name in OPTIONAL_INDEXES)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connectable = create_engine(_url(), poolclass=pool.NullPool, future=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
