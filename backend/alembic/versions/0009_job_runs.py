"""Журнал запусков фоновых задач

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-08 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'job_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job', sa.String(length=64), nullable=False),
        sa.Column('run_key', sa.String(length=120), nullable=False),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column(
            'started_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        # Уникальность ключа — и есть защита от повторной рассылки.
        sa.UniqueConstraint('run_key', name='uq_job_runs_run_key'),
    )
    op.create_index('ix_job_runs_job', 'job_runs', ['job', 'started_at'])


def downgrade() -> None:
    op.drop_index('ix_job_runs_job', table_name='job_runs')
    op.drop_table('job_runs')
