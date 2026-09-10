"""Временный пароль: обязательная смена

Пароль, выданный администратором, знают двое. Работать под ним нельзя:
заявка, поданная так, не доказывает, кто её подал. Признак снимается,
когда человек задаёт свой пароль сам.

Существующим сотрудникам ставится false: их пароли выданы до появления
правила, и запирать всю компанию задним числом — не исправление, а
остановка работы.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-10 18:30:30.438766
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0020'
down_revision: str | None = '0019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column(
            'must_change_password',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Значение по умолчанию нужно было только для существующих строк:
    # дальше его задаёт приложение, и лишнее умолчание в схеме
    # однажды скроет забытое поле.
    op.alter_column('employees', 'must_change_password', server_default=None)


def downgrade() -> None:
    op.drop_column('employees', 'must_change_password')
