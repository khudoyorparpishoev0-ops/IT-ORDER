"""Поля категории расхода: питание, командировка, карго и остальные.

У заявки появляется `details` — поля, которых нет у сметы строками:
человек и дней у питания, маршрут и даты у командировки, вес и таможня
у карго. Набор задаёт категория (`app/services/categories.py`), проверяет
его сервер.

Схема больше ничего не требует. Две новые категории (`CARGO`,
`CONNECTIVITY`) — это новые значения перечисления, а оно хранится
обычным `varchar(16)` без CHECK-ограничения: `Enum(native_enum=False)` в
SQLAlchemy 2.0 ограничение не создаёт. Проверять новые значения будет
приложение, как и прежние.

Задним числом ничего не заполняется: у заявок, поданных до появления
категорийных форм, `details` пустой, а категория часто и вовсе не
указана. Такие заявки продолжают работать по-старому — сметой строками
через отдел закупа.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default нужен только на время заливки: в таблице уже есть
    # строки, а колонка обязательная. Дальше значение ставит приложение.
    op.add_column(
        "expense_requests",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("expense_requests", "details", server_default=None)


def downgrade() -> None:
    op.drop_column("expense_requests", "details")
