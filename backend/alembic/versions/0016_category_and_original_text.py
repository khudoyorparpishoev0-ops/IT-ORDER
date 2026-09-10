"""Бизнес-категория заявки и исходный ввод сотрудника

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-10 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = (
    'MATERIALS', 'EQUIPMENT', 'TRANSPORT', 'FUEL', 'MEALS', 'LODGING',
    'TRIP', 'DELIVERY', 'SERVICES', 'HOUSEHOLD', 'OTHER',
)


def upgrade() -> None:
    op.add_column(
        'expense_requests',
        sa.Column(
            'category',
            sa.Enum(*CATEGORIES, name='request_category', native_enum=False, length=16),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_requests_category_created', 'expense_requests', ['category', 'created_at']
    )

    op.add_column(
        'expense_lines',
        sa.Column('original_text', sa.String(length=200), nullable=False, server_default=''),
    )
    # У заявок, поданных до этой ревизии, исходного ввода нет: он не
    # сохранялся. Ближайшее, что о нём известно, — итоговое название.
    # Заполняем им, чтобы аналитика не спотыкалась о пустое поле, но в
    # документации это оговорено: для старых строк original_text = title.
    op.execute('UPDATE expense_lines SET original_text = title')
    op.alter_column('expense_lines', 'original_text', server_default=None)


def downgrade() -> None:
    op.drop_column('expense_lines', 'original_text')
    op.drop_index('ix_requests_category_created', table_name='expense_requests')
    op.drop_column('expense_requests', 'category')
