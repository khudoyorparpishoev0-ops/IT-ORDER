"""Приведённое написание материала и алиасы, накопленные из поправок

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-09 23:40:00.000000
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Правила нормализации на момент этой ревизии. Скопированы из
# app/services/material_norm.py намеренно: миграция должна делать одно и
# то же и через год, когда правила в приложении изменятся. Иначе
# повторный прогон на чистой базе даст не тот результат, что тогда.
_SUPERSCRIPT = str.maketrans({"²": "2", "³": "3"})
_PUNCT = re.compile(r"[^0-9a-zа-я]+")
_JOINT = re.compile(r"(?<=[a-zа-я])(?=[0-9])|(?<=[0-9])(?=[a-zа-я])")


def _normalize(text: str | None) -> str:
    value = (text or "").casefold().replace("ё", "е")
    value = value.translate(_SUPERSCRIPT)
    value = _PUNCT.sub(" ", value)
    value = _JOINT.sub(" ", value)
    return " ".join(value.split())


def upgrade() -> None:
    op.add_column(
        'expense_lines',
        sa.Column('normalized_text', sa.String(length=200), nullable=False, server_default=''),
    )

    # Заполняем то, что уже подано: без этого подсказки и поиск дублей не
    # увидели бы ни одной старой заявки.
    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT id, title FROM expense_lines')).fetchall()
    for line_id, title in rows:
        conn.execute(
            sa.text('UPDATE expense_lines SET normalized_text = :value WHERE id = :id'),
            {'value': _normalize(title)[:200], 'id': line_id},
        )

    op.alter_column('expense_lines', 'normalized_text', server_default=None)
    op.create_index('ix_lines_normalized', 'expense_lines', ['normalized_text'])

    op.create_table(
        'material_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alias', sa.String(length=200), nullable=False),
        sa.Column('canonical', sa.String(length=200), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('uses', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alias', name='uq_material_aliases_alias'),
    )


def downgrade() -> None:
    op.drop_table('material_aliases')
    op.drop_index('ix_lines_normalized', table_name='expense_lines')
    op.drop_column('expense_lines', 'normalized_text')
