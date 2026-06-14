"""add optional subcategory to expenses and vendor rules

Revision ID: 030
Revises: 029
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("finance_expense_entries") as batch_op:
        batch_op.add_column(sa.Column("subcategory", sa.String(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_finance_expense_entries_subcategory"),
            ["subcategory"],
            unique=False,
        )

    with op.batch_alter_table("finance_vendor_categories") as batch_op:
        batch_op.add_column(sa.Column("subcategory", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("finance_vendor_categories") as batch_op:
        batch_op.drop_column("subcategory")

    with op.batch_alter_table("finance_expense_entries") as batch_op:
        batch_op.drop_index(batch_op.f("ix_finance_expense_entries_subcategory"))
        batch_op.drop_column("subcategory")
