"""add source field to securities tax lots

Revision ID: 014
Revises: 013
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="statement",
            )
        )
        batch_op.create_index("ix_securities_source", ["source"])

    with op.batch_alter_table("securities") as batch_op:
        batch_op.alter_column("source", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.drop_index("ix_securities_source")
        batch_op.drop_column("source")
