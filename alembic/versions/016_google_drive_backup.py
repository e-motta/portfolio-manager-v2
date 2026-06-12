"""add google drive backup fields to users

Revision ID: 016
Revises: 015
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlmodel
from alembic import op
import sqlalchemy as sa

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "google_refresh_token",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "google_drive_folder_id",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("google_drive_folder_id")
        batch_op.drop_column("google_refresh_token")
