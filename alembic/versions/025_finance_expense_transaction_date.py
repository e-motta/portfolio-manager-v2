"""add optional transaction date to finance expenses

Revision ID: 025
Revises: 024
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("finance_expense_entries") as batch_op:
        batch_op.add_column(sa.Column("transaction_date", sa.Date(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_finance_expense_entries_transaction_date"),
            ["transaction_date"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("finance_expense_entries") as batch_op:
        batch_op.drop_index(batch_op.f("ix_finance_expense_entries_transaction_date"))
        batch_op.drop_column("transaction_date")
