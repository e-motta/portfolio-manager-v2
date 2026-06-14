"""add source and external_id to finance transfers

Revision ID: 032
Revises: 031
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("finance_transfer_entries") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(), nullable=False, server_default="manual")
        )
        batch_op.add_column(sa.Column("external_id", sa.String(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_finance_transfer_entries_source"),
            ["source"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_finance_transfer_entries_external_id"),
            ["external_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("finance_transfer_entries") as batch_op:
        batch_op.drop_index(batch_op.f("ix_finance_transfer_entries_external_id"))
        batch_op.drop_index(batch_op.f("ix_finance_transfer_entries_source"))
        batch_op.drop_column("external_id")
        batch_op.drop_column("source")
