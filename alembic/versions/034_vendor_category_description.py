"""add description to finance vendor categories

Revision ID: 034
Revises: 033
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("finance_vendor_categories") as batch_op:
        batch_op.add_column(
            sa.Column("description", sa.String(), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("finance_vendor_categories") as batch_op:
        batch_op.drop_column("description")
