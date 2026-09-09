"""Журнал обращений к AI-помощнику

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-09 23:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_interactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('MATERIAL', 'REQUEST', 'ANALYTICS', name='ai_kind', native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column(
            'source',
            sa.Enum('WEB', 'TELEGRAM', name='ai_source', native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(length=200), nullable=True),
        sa.Column('question', sa.Text(), nullable=True),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('applied', sa.Boolean(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_created_at', 'ai_interactions', ['created_at'])
    op.create_index('ix_ai_employee', 'ai_interactions', ['employee_id'])
    op.create_index('ix_ai_kind_created', 'ai_interactions', ['kind', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_ai_kind_created', table_name='ai_interactions')
    op.drop_index('ix_ai_employee', table_name='ai_interactions')
    op.drop_index('ix_ai_created_at', table_name='ai_interactions')
    op.drop_table('ai_interactions')
