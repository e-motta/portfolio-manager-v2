"""finance refactor: income categories, investment entries, drop summary amounts

Revision ID: 028
Revises: 027
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlmodel import Session

    from app.services.finance import migrate_finance_summary_to_entries

    bind = op.get_bind()
    inspector = inspect(bind)
    income_columns = {col["name"] for col in inspector.get_columns("finance_income_entries")}

    if "category" not in income_columns:
        op.add_column(
            "finance_income_entries",
            sa.Column("category", sa.String(), nullable=False, server_default="Outros"),
        )
        op.create_index(
            "ix_finance_income_entries_category",
            "finance_income_entries",
            ["category"],
        )

    if "finance_investment_entries" not in inspector.get_table_names():
        op.create_table(
            "finance_investment_entries",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("broker", sa.String(), nullable=False),
            sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "year", "month", "broker"),
        )
        op.create_index(
            "ix_finance_investment_entries_user_id",
            "finance_investment_entries",
            ["user_id"],
        )
        op.create_index(
            "ix_finance_investment_entries_year",
            "finance_investment_entries",
            ["year"],
        )
        op.create_index(
            "ix_finance_investment_entries_broker",
            "finance_investment_entries",
            ["broker"],
        )

    if "finance_summary_amounts" in inspector.get_table_names():
        with Session(bind) as session:
            migrate_finance_summary_to_entries(session)

        op.drop_index(
            "ix_finance_summary_amounts_user_year_line_month",
            table_name="finance_summary_amounts",
        )
        op.drop_index(
            "ix_finance_summary_amounts_line_key", table_name="finance_summary_amounts"
        )
        op.drop_index(
            "ix_finance_summary_amounts_year", table_name="finance_summary_amounts"
        )
        op.drop_index(
            "ix_finance_summary_amounts_user_id", table_name="finance_summary_amounts"
        )
        op.drop_table("finance_summary_amounts")


def downgrade() -> None:
    pass
