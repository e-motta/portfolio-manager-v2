"""add open finance fields to finance income entries

Revision ID: 021
Revises: 020
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlmodel
from alembic import op
import sqlalchemy as sa

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("finance_income_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(
            sa.Column(
                "external_id",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )

    op.create_index(
        "ix_finance_income_open_finance_external",
        "finance_income_entries",
        ["user_id", "source", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_income_open_finance_external",
        table_name="finance_income_entries",
    )

    with op.batch_alter_table("finance_income_entries") as batch_op:
        batch_op.drop_column("external_id")
        batch_op.drop_column("source")
