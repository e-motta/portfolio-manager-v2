"""add finance income, expense, and summary tables

Revision ID: 017
Revises: 016
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_income_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finance_income_entries_user_id",
        "finance_income_entries",
        ["user_id"],
    )
    op.create_index(
        "ix_finance_income_entries_year",
        "finance_income_entries",
        ["year"],
    )

    op.create_table(
        "finance_expense_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("vendor", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payment_account", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finance_expense_entries_user_id",
        "finance_expense_entries",
        ["user_id"],
    )
    op.create_index(
        "ix_finance_expense_entries_year",
        "finance_expense_entries",
        ["year"],
    )
    op.create_index(
        "ix_finance_expense_entries_category",
        "finance_expense_entries",
        ["category"],
    )
    op.create_index(
        "ix_finance_expense_entries_payment_account",
        "finance_expense_entries",
        ["payment_account"],
    )

    op.create_table(
        "finance_summary_amounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("line_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finance_summary_amounts_user_id",
        "finance_summary_amounts",
        ["user_id"],
    )
    op.create_index(
        "ix_finance_summary_amounts_year",
        "finance_summary_amounts",
        ["year"],
    )
    op.create_index(
        "ix_finance_summary_amounts_line_key",
        "finance_summary_amounts",
        ["line_key"],
    )
    op.create_index(
        "ix_finance_summary_amounts_user_year_line_month",
        "finance_summary_amounts",
        ["user_id", "year", "line_key", "month"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_summary_amounts_user_year_line_month",
        table_name="finance_summary_amounts",
    )
    op.drop_index("ix_finance_summary_amounts_line_key", table_name="finance_summary_amounts")
    op.drop_index("ix_finance_summary_amounts_year", table_name="finance_summary_amounts")
    op.drop_index("ix_finance_summary_amounts_user_id", table_name="finance_summary_amounts")
    op.drop_table("finance_summary_amounts")

    op.drop_index(
        "ix_finance_expense_entries_payment_account",
        table_name="finance_expense_entries",
    )
    op.drop_index("ix_finance_expense_entries_category", table_name="finance_expense_entries")
    op.drop_index("ix_finance_expense_entries_year", table_name="finance_expense_entries")
    op.drop_index("ix_finance_expense_entries_user_id", table_name="finance_expense_entries")
    op.drop_table("finance_expense_entries")

    op.drop_index("ix_finance_income_entries_year", table_name="finance_income_entries")
    op.drop_index("ix_finance_income_entries_user_id", table_name="finance_income_entries")
    op.drop_table("finance_income_entries")
