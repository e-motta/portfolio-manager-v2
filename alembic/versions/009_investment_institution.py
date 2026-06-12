"""add institution field to investments

Revision ID: 009
Revises: 008
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("investments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "institution",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.create_index("ix_investments_institution", ["institution"])

    with op.batch_alter_table("investments") as batch_op:
        batch_op.alter_column("institution", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("investments") as batch_op:
        batch_op.drop_index("ix_investments_institution")
        batch_op.drop_column("institution")
