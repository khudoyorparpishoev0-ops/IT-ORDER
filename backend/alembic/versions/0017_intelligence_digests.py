"""Автоматические сводки ORDER Intelligence: настройки и история доставок

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-10 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTINGS = (
    ('intelligence_enabled', sa.Boolean(), 'false'),
    ('digest_morning_enabled', sa.Boolean(), 'true'),
    ('digest_evening_enabled', sa.Boolean(), 'true'),
    ('critical_alerts_enabled', sa.Boolean(), 'true'),
    ('digest_when_no_changes', sa.Boolean(), 'false'),
)


def upgrade() -> None:
    # Главный выключатель по умолчанию выключен: включать людям рассылку
    # без их ведома нельзя, даже полезную.
    for name, kind, default in SETTINGS:
        op.add_column(
            'employees',
            sa.Column(name, kind, nullable=False, server_default=sa.text(default)),
        )
    op.add_column(
        'employees',
        sa.Column(
            'digest_morning_time',
            sa.Time(),
            nullable=False,
            server_default=sa.text("'09:00:00'"),
        ),
    )
    op.add_column(
        'employees',
        sa.Column(
            'digest_evening_time',
            sa.Time(),
            nullable=False,
            server_default=sa.text("'18:00:00'"),
        ),
    )
    # Пусто — корпоративный пояс из APP_TIMEZONE.
    op.add_column('employees', sa.Column('timezone', sa.String(length=64), nullable=True))

    for name, _, _ in SETTINGS:
        op.alter_column('employees', name, server_default=None)
    op.alter_column('employees', 'digest_morning_time', server_default=None)
    op.alter_column('employees', 'digest_evening_time', server_default=None)

    op.create_table(
        'intelligence_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum(
                'MORNING', 'EVENING', 'CRITICAL',
                name='intelligence_kind', native_enum=False, length=16,
            ),
            nullable=False,
        ),
        sa.Column('dedup_key', sa.String(length=200), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_count', sa.Integer(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'channel',
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'telegram'"),
        ),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('result_count', sa.Integer(), nullable=False),
        sa.Column('ai_used', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['request_id'], ['expense_requests.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        # Ключ уникален — на нём и держится защита от повторов: вставка
        # либо проходит, либо нет, и гонку решает база, а не порядок
        # запуска процессов.
        sa.UniqueConstraint('dedup_key', name='uq_intelligence_dedup'),
    )
    op.create_index('ix_intel_employee_kind', 'intelligence_deliveries', ['employee_id', 'kind'])
    op.create_index('ix_intel_created', 'intelligence_deliveries', ['created_at'])
    op.create_index('ix_intel_unresolved', 'intelligence_deliveries', ['resolved_at'])


def downgrade() -> None:
    op.drop_index('ix_intel_unresolved', table_name='intelligence_deliveries')
    op.drop_index('ix_intel_created', table_name='intelligence_deliveries')
    op.drop_index('ix_intel_employee_kind', table_name='intelligence_deliveries')
    op.drop_table('intelligence_deliveries')
    op.drop_column('employees', 'timezone')
    op.drop_column('employees', 'digest_evening_time')
    op.drop_column('employees', 'digest_morning_time')
    for name, _, _ in reversed(SETTINGS):
        op.drop_column('employees', name)


