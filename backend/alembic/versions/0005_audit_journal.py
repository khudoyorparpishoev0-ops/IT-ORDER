"""Журнал действий: сотрудник, адрес, индексы

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-07 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('audit_log', sa.Column('employee_id', sa.Integer(), nullable=True))
    op.add_column('audit_log', sa.Column('ip', sa.String(length=45), nullable=True))
    op.create_foreign_key(
        'fk_audit_log_employee_id',
        'audit_log',
        'employees',
        ['employee_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_audit_created_at', 'audit_log', ['created_at'])
    op.create_index('ix_audit_employee', 'audit_log', ['employee_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_employee', table_name='audit_log')
    op.drop_index('ix_audit_created_at', table_name='audit_log')
    op.drop_constraint('fk_audit_log_employee_id', 'audit_log', type_='foreignkey')
    op.drop_column('audit_log', 'ip')
    op.drop_column('audit_log', 'employee_id')
