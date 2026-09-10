"""Шаблоны заявок, оценки ответов помощника и метаданные обращений

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-10 01:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger('alembic.runtime.migration')


def upgrade() -> None:
    op.create_table(
        'ai_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interaction_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('useful', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        # Оценка живёт ровно столько, сколько живёт сам ответ: чистка
        # журнала по сроку хранения уносит её вместе с обращением.
        sa.ForeignKeyConstraint(['interaction_id'], ['ai_interactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('interaction_id', 'employee_id', name='uq_ai_feedback_once'),
    )
    op.create_index('ix_ai_feedback_created', 'ai_feedback', ['created_at'])

    op.create_table(
        'request_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'name', name='uq_template_name_per_employee'),
    )
    op.create_index('ix_templates_employee', 'request_templates', ['employee_id'])

    # Стоимость ORDER AI считается по токенам. Если Anthropic их не
    # вернул, колонки останутся пустыми — метрики это переживают.
    op.add_column('ai_interactions', sa.Column('model', sa.String(length=64), nullable=True))
    op.add_column('ai_interactions', sa.Column('input_tokens', sa.Integer(), nullable=True))
    op.add_column('ai_interactions', sa.Column('output_tokens', sa.Integer(), nullable=True))

    # Нечёткий поиск по написанию. Расширение ставим, только если база
    # даёт: на чужом кластере прав может не быть, а поиск обязан работать
    # и без него — через ILIKE. Падать из-за ускорения нельзя.
    try:
        with op.get_context().autocommit_block():
            op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
            op.execute(
                'CREATE INDEX IF NOT EXISTS ix_lines_normalized_trgm '
                'ON expense_lines USING gin (normalized_text gin_trgm_ops)'
            )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            'pg_trgm не поставлен (%s). Поиск будет работать через ILIKE, '
            'просто медленнее на больших объёмах.',
            exc,
        )


def downgrade() -> None:
    try:
        op.execute('DROP INDEX IF EXISTS ix_lines_normalized_trgm')
    except Exception:  # noqa: BLE001
        pass
    op.drop_column('ai_interactions', 'output_tokens')
    op.drop_column('ai_interactions', 'input_tokens')
    op.drop_column('ai_interactions', 'model')
    op.drop_index('ix_templates_employee', table_name='request_templates')
    op.drop_table('request_templates')
    op.drop_index('ix_ai_feedback_created', table_name='ai_feedback')
    op.drop_table('ai_feedback')
