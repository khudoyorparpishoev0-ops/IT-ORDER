"""Склад: номенклатура, места хранения, движения и остатки.

Только новые таблицы и одна последовательность. Ни одна существующая
колонка не меняется и не удаляется: боевая база после этой ревизии
теряет ровно ничего, а путь заявки продолжает работать как прежде.

Новая роль `WAREHOUSE` — это новое значение перечисления, а оно хранится
обычным `varchar(16)` без CHECK-ограничения (`Enum(native_enum=False)`
ограничение не создаёт). Менять базу под роль не требуется.

Главное в схеме — `CHECK (quantity >= 0)` у остатка. Проверка в сервисе
объясняет человеку, чего не хватает; отрицательный остаток не даёт
записать именно это ограничение, и обойти его не может ни будущий код,
ни прямой SQL.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("stock_document_number_seq")))

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("keeper_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["keeper_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_warehouses_keeper", "warehouses", ["keeper_id"])
    op.create_index("ix_warehouses_project", "warehouses", ["project_id"])

    op.create_table(
        "stock_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("article", sa.String(length=64), nullable=True),
        sa.Column("min_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("track_serial", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("min_quantity >= 0", name="ck_stock_items_min_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_stock_items_active_name", "stock_items", ["active", "name"])

    op.create_table(
        "stock_balances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_balance_non_negative"),
        sa.ForeignKeyConstraint(["item_id"], ["stock_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_id", "item_id", name="uq_stock_balance_pair"),
    )
    op.create_index("ix_stock_balances_item", "stock_balances", ["item_id"])

    op.create_table(
        "stock_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column("recipient_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("supplier", sa.String(length=200), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(length=200), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["expense_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index("ix_stock_docs_employee", "stock_documents", ["employee_id"])
    op.create_index("ix_stock_docs_kind_created", "stock_documents", ["kind", "created_at"])
    op.create_index("ix_stock_docs_project", "stock_documents", ["project_id"])
    op.create_index("ix_stock_docs_recipient", "stock_documents", ["recipient_id"])
    op.create_index("ix_stock_docs_request", "stock_documents", ["request_id"])
    op.create_index(
        "ix_stock_docs_warehouse", "stock_documents", ["warehouse_id", "created_at"]
    )

    op.create_table(
        "stock_document_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("comment", sa.String(length=200), nullable=True),
        sa.CheckConstraint("price IS NULL OR price >= 0", name="ck_stock_doc_line_price"),
        sa.CheckConstraint("quantity > 0", name="ck_stock_doc_line_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["stock_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["item_id"], ["stock_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_doc_lines_document", "stock_document_lines", ["document_id"])
    op.create_index("ix_stock_doc_lines_item", "stock_document_lines", ["item_id"])

    op.create_table(
        "stock_moves",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity <> 0", name="ck_stock_move_quantity_nonzero"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["stock_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["item_id"], ["stock_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_moves_document", "stock_moves", ["document_id"])
    op.create_index("ix_stock_moves_employee", "stock_moves", ["employee_id"])
    op.create_index("ix_stock_moves_item_created", "stock_moves", ["item_id", "created_at"])
    op.create_index(
        "ix_stock_moves_warehouse_created", "stock_moves", ["warehouse_id", "created_at"]
    )

    op.create_table(
        "stock_serials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("serial", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
        sa.Column("holder_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("received_move_id", sa.Integer(), nullable=True),
        sa.Column("issued_move_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["holder_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issued_move_id"], ["stock_moves.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["item_id"], ["stock_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["received_move_id"], ["stock_moves.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "serial", name="uq_stock_serial_per_item"),
    )
    op.create_index("ix_stock_serials_holder", "stock_serials", ["holder_id"])
    op.create_index("ix_stock_serials_issued", "stock_serials", ["issued_move_id"])
    op.create_index("ix_stock_serials_project", "stock_serials", ["project_id"])
    op.create_index("ix_stock_serials_received", "stock_serials", ["received_move_id"])
    op.create_index("ix_stock_serials_status", "stock_serials", ["status"])
    op.create_index("ix_stock_serials_warehouse", "stock_serials", ["warehouse_id"])


def downgrade() -> None:
    op.drop_table("stock_serials")
    op.drop_table("stock_moves")
    op.drop_table("stock_document_lines")
    op.drop_table("stock_documents")
    op.drop_table("stock_balances")
    op.drop_table("stock_items")
    op.drop_table("warehouses")
    op.execute(sa.schema.DropSequence(sa.Sequence("stock_document_number_seq")))
