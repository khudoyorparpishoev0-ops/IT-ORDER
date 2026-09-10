"""Индексы для внешних ключей

Три ссылки на другие таблицы жили без индекса. На нынешних объёмах это
незаметно, но два запроса из них — не редкие: отчёт по объекту и проверка
«есть ли у объекта заявки» перед его отключением. Оба идут перебором всей
таблицы заявок, и с ростом истории это только ухудшается.

Данные миграция не трогает: только добавляет индексы.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-10 16:13:34.281930
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index('ix_requests_project', 'expense_requests', ['project_id'], unique=False)
    op.create_index('ix_intel_request', 'intelligence_deliveries', ['request_id'], unique=False)
    op.create_index('ix_templates_project', 'request_templates', ['project_id'], unique=False)
    op.create_index('ix_ai_feedback_employee', 'ai_feedback', ['employee_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_feedback_employee', table_name='ai_feedback')
    op.drop_index('ix_templates_project', table_name='request_templates')
    op.drop_index('ix_intel_request', table_name='intelligence_deliveries')
    op.drop_index('ix_requests_project', table_name='expense_requests')
