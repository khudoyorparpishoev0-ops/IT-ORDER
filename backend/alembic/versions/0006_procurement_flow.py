"""Путь через отдел закупа: заявка без цен, склад, оценка

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-07 22:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- строки: единица, склад, цена может быть ещё не известна ---------
    op.add_column('expense_lines', sa.Column('unit', sa.String(length=32), nullable=True))
    op.add_column(
        'expense_lines',
        sa.Column('from_stock', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('expense_lines', 'from_stock', server_default=None)
    op.alter_column('expense_lines', 'price', existing_type=sa.Numeric(12, 2), nullable=True)
    op.alter_column('expense_lines', 'total', existing_type=sa.Numeric(12, 2), nullable=True)

    # Ограничения переписываем: NULL теперь допустим.
    op.drop_constraint('ck_lines_price_non_negative', 'expense_lines', type_='check')
    op.drop_constraint('ck_lines_total_non_negative', 'expense_lines', type_='check')
    op.create_check_constraint(
        'ck_lines_price_non_negative', 'expense_lines', 'price IS NULL OR price >= 0'
    )
    op.create_check_constraint(
        'ck_lines_total_non_negative', 'expense_lines', 'total IS NULL OR total >= 0'
    )

    # --- заявка: кто и когда оценил ---------------------------------------
    op.add_column(
        'expense_requests', sa.Column('sourced_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'expense_requests', sa.Column('sourced_by', sa.String(length=200), nullable=True)
    )
    op.add_column('expense_requests', sa.Column('sourcing_comment', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('expense_requests', 'sourcing_comment')
    op.drop_column('expense_requests', 'sourced_by')
    op.drop_column('expense_requests', 'sourced_at')

    # Строки без цены в старую схему не помещаются: они появились вместе
    # с путём через закуп. Проставляем нули, чтобы откат не падал.
    op.execute('UPDATE expense_lines SET price = 0 WHERE price IS NULL')
    op.execute('UPDATE expense_lines SET total = 0 WHERE total IS NULL')

    op.drop_constraint('ck_lines_price_non_negative', 'expense_lines', type_='check')
    op.drop_constraint('ck_lines_total_non_negative', 'expense_lines', type_='check')
    op.alter_column('expense_lines', 'price', existing_type=sa.Numeric(12, 2), nullable=False)
    op.alter_column('expense_lines', 'total', existing_type=sa.Numeric(12, 2), nullable=False)
    op.create_check_constraint('ck_lines_price_non_negative', 'expense_lines', 'price >= 0')
    op.create_check_constraint('ck_lines_total_non_negative', 'expense_lines', 'total >= 0')

    op.drop_column('expense_lines', 'from_stock')
    op.drop_column('expense_lines', 'unit')
