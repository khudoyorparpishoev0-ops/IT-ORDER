"""История действий по заявке: кто сделал, что изменилось, кто открывал.

У события заявки появляется ссылка на сотрудника (`employee_id`), его роль
на момент действия (`actor_role`), признак «человек или система»
(`actor_type`) и подробности (`details`): «было → стало» по статусу и
сумме, состав правки черновика, цены по позициям, у кого заявка теперь.
Имя строкой (`actor`) остаётся: сотрудника переименуют или удалят, а
история должна читаться и через год. Роль — тоже снимок: закупщика
переведут в руководители, и «Оценил заявку · Руководитель» станет
неправдой про уже случившееся.

`request_views` отвечает на вопрос, которого раньше не было ни у кого:
заявка просто лежит у человека или он её действительно открыл. Одна
строка на пару «заявка + сотрудник», а не событие на каждое открытие:
лента из просмотров вытеснила бы то, ради чего её открывают.

Задним числом ничего не размечается: у событий, записанных до этой
ревизии, `employee_id` пустой, а `actor_type` — «human». Кто именно
нажимал кнопку два месяца назад, мы не знаем, и подставлять догадку в
журнал нельзя. Имя в `actor` у них есть — этого достаточно, чтобы
старая часть ленты читалась.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "request_events", sa.Column("employee_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_request_events_employee",
        "request_events",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_request_events_employee", "request_events", ["employee_id"], unique=False
    )
    # Роль на момент действия. Задним числом не проставляется: закупщика
    # могли перевести в руководители, и нынешняя роль сказала бы про
    # прошлое действие неправду.
    op.add_column("request_events", sa.Column("actor_role", sa.String(length=16)))
    # server_default нужен только на время заливки: в таблице уже есть
    # строки, а колонка обязательная. Дальше значение ставит приложение.
    op.add_column(
        "request_events",
        sa.Column(
            "actor_type",
            sa.String(length=8),
            nullable=False,
            server_default="human",
        ),
    )
    op.add_column(
        "request_events",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("request_events", "actor_type", server_default=None)
    op.alter_column("request_events", "details", server_default=None)

    op.create_table(
        "request_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column(
            "first_viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("times", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["expense_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "employee_id", name="uq_request_view_once"),
    )
    op.create_index(
        "ix_request_views_employee", "request_views", ["employee_id"], unique=False
    )
    op.create_index(
        "ix_request_views_request", "request_views", ["request_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_request_views_request", table_name="request_views")
    op.drop_index("ix_request_views_employee", table_name="request_views")
    op.drop_table("request_views")
    op.drop_index("ix_request_events_employee", table_name="request_events")
    op.drop_constraint(
        "fk_request_events_employee", "request_events", type_="foreignkey"
    )
    op.drop_column("request_events", "details")
    op.drop_column("request_events", "actor_type")
    op.drop_column("request_events", "actor_role")
    op.drop_column("request_events", "employee_id")
