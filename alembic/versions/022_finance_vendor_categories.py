"""add finance vendor category rules

Revision ID: 022
Revises: 021
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlmodel
from alembic import op
import sqlalchemy as sa

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_vendor_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "vendor_key"),
    )
    with op.batch_alter_table("finance_vendor_categories") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_finance_vendor_categories_user_id"),
            ["user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_finance_vendor_categories_vendor_key"),
            ["vendor_key"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_finance_vendor_categories_category"),
            ["category"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("finance_vendor_categories")
