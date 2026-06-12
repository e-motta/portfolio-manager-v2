"""replace investment original/market values with current value

Revision ID: 010
Revises: 009
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("investments") as batch_op:
        batch_op.alter_column("market_value", new_column_name="current_value")
        batch_op.drop_column("original_value")


def downgrade() -> None:
    with op.batch_alter_table("investments") as batch_op:
        batch_op.add_column(
            sa.Column("original_value", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0")
        )
        batch_op.alter_column("current_value", new_column_name="market_value")
        batch_op.alter_column("original_value", server_default=None)
