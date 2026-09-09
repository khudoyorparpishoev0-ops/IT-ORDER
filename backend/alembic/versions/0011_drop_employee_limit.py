"""Лимитов сотрудников нет: расход считается по объектам

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-09 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('ck_employees_limit_non_negative', 'employees', type_='check')
    op.drop_column('employees', 'monthly_limit')


def downgrade() -> None:
    op.add_column('employees', sa.Column('monthly_limit', sa.Numeric(precision=12, scale=2), nullable=True))
    op.create_check_constraint(
        'ck_employees_limit_non_negative', 'employees', 'monthly_limit IS NULL OR monthly_limit >= 0'
    )
