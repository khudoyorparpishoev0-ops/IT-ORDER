"""Привязка Telegram к сотруднику

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-08 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('employees', sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True))
    op.add_column('employees', sa.Column('telegram_username', sa.String(length=64), nullable=True))
    op.add_column(
        'employees', sa.Column('telegram_linked_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('employees', sa.Column('telegram_link_code', sa.String(length=32), nullable=True))
    op.add_column(
        'employees',
        sa.Column('telegram_link_expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint('uq_employees_telegram_chat', 'employees', ['telegram_chat_id'])
    op.create_index('ix_employees_telegram_code', 'employees', ['telegram_link_code'])


def downgrade() -> None:
    op.drop_index('ix_employees_telegram_code', table_name='employees')
    op.drop_constraint('uq_employees_telegram_chat', 'employees', type_='unique')
    op.drop_column('employees', 'telegram_link_expires_at')
    op.drop_column('employees', 'telegram_link_code')
    op.drop_column('employees', 'telegram_linked_at')
    op.drop_column('employees', 'telegram_username')
    op.drop_column('employees', 'telegram_chat_id')
