"""add finance transfer entries table

Revision ID: 031
Revises: 030
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_transfer_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("from_account", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("to_account", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finance_transfer_entries_user_id",
        "finance_transfer_entries",
        ["user_id"],
    )
    op.create_index(
        "ix_finance_transfer_entries_year",
        "finance_transfer_entries",
        ["year"],
    )
    op.create_index(
        "ix_finance_transfer_entries_transaction_date",
        "finance_transfer_entries",
        ["transaction_date"],
    )
    op.create_index(
        "ix_finance_transfer_entries_from_account",
        "finance_transfer_entries",
        ["from_account"],
    )
    op.create_index(
        "ix_finance_transfer_entries_to_account",
        "finance_transfer_entries",
        ["to_account"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_transfer_entries_to_account",
        table_name="finance_transfer_entries",
    )
    op.drop_index(
        "ix_finance_transfer_entries_from_account",
        table_name="finance_transfer_entries",
    )
    op.drop_index(
        "ix_finance_transfer_entries_transaction_date",
        table_name="finance_transfer_entries",
    )
    op.drop_index(
        "ix_finance_transfer_entries_year",
        table_name="finance_transfer_entries",
    )
    op.drop_index(
        "ix_finance_transfer_entries_user_id",
        table_name="finance_transfer_entries",
    )
    op.drop_table("finance_transfer_entries")
