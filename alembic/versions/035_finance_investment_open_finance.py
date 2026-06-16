"""add finance investment open finance import tracking

Revision ID: 035
Revises: 034
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_investment_open_finance_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "external_id"),
    )
    op.create_index(
        op.f("ix_finance_investment_open_finance_imports_broker"),
        "finance_investment_open_finance_imports",
        ["broker"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_investment_open_finance_imports_external_id"),
        "finance_investment_open_finance_imports",
        ["external_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_investment_open_finance_imports_user_id"),
        "finance_investment_open_finance_imports",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_investment_open_finance_imports_year"),
        "finance_investment_open_finance_imports",
        ["year"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_finance_investment_open_finance_imports_year"),
        table_name="finance_investment_open_finance_imports",
    )
    op.drop_index(
        op.f("ix_finance_investment_open_finance_imports_user_id"),
        table_name="finance_investment_open_finance_imports",
    )
    op.drop_index(
        op.f("ix_finance_investment_open_finance_imports_external_id"),
        table_name="finance_investment_open_finance_imports",
    )
    op.drop_index(
        op.f("ix_finance_investment_open_finance_imports_broker"),
        table_name="finance_investment_open_finance_imports",
    )
    op.drop_table("finance_investment_open_finance_imports")
