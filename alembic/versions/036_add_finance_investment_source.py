"""add source column to finance investment entries

Revision ID: 036
Revises: 035
Create Date: 2026-10-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("finance_investment_entries")}
    if "source" not in columns:
        op.add_column(
            "finance_investment_entries",
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        )
        op.create_index(
            "ix_finance_investment_entries_source",
            "finance_investment_entries",
            ["source"],
        )

    existing_constraints = {
        c["name"] for c in inspector.get_unique_constraints("finance_investment_entries")
    }
    if "finance_investment_entries_user_id_year_month_broker_key" in existing_constraints:
        op.drop_constraint(
            "finance_investment_entries_user_id_year_month_broker_key",
            "finance_investment_entries",
            type_="unique",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_constraints = {
        c["name"] for c in inspector.get_unique_constraints("finance_investment_entries")
    }
    if "finance_investment_entries_user_id_year_month_broker_key" not in existing_constraints:
        op.create_unique_constraint(
            "finance_investment_entries_user_id_year_month_broker_key",
            "finance_investment_entries",
            ["user_id", "year", "month", "broker"],
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("finance_investment_entries")}
    if "ix_finance_investment_entries_source" in indexes:
        op.drop_index(
            "ix_finance_investment_entries_source",
            table_name="finance_investment_entries",
        )

    columns = {col["name"] for col in inspector.get_columns("finance_investment_entries")}
    if "source" in columns:
        op.drop_column("finance_investment_entries", "source")
