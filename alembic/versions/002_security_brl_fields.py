"""add security brl fields

Revision ID: 002
Revises: 001
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.add_column(sa.Column("purchase_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("usd_brl_rate", sa.Numeric(precision=12, scale=6), nullable=True)
        )
        batch_op.add_column(
            sa.Column("price_brl", sa.Numeric(precision=18, scale=8), nullable=True)
        )

    op.execute(
        """
        UPDATE securities
        SET purchase_date = date(created_at),
            usd_brl_rate = 1,
            price_brl = latest_price
        WHERE purchase_date IS NULL
        """
    )

    with op.batch_alter_table("securities") as batch_op:
        batch_op.alter_column("purchase_date", nullable=False)
        batch_op.alter_column("usd_brl_rate", nullable=False)
        batch_op.alter_column("price_brl", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.drop_column("price_brl")
        batch_op.drop_column("usd_brl_rate")
        batch_op.drop_column("purchase_date")
