"""add portfolio snapshots

Revision ID: 011
Revises: 010
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date"),
    )
    op.create_index("ix_portfolio_snapshots_snapshot_date", "portfolio_snapshots", ["snapshot_date"])

    op.create_table(
        "snapshot_asset_classes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type_id", sa.Uuid(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("current_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("current_weight", sa.Numeric(precision=7, scale=6), nullable=False),
        sa.Column("target_weight", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.ForeignKeyConstraint(["asset_type_id"], ["asset_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["portfolio_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "snapshot_investments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("institution", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("asset_type_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("current_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["portfolio_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "snapshot_holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("total_position", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("current_value_brl", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["portfolio_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("snapshot_holdings")
    op.drop_table("snapshot_investments")
    op.drop_table("snapshot_asset_classes")
    op.drop_index("ix_portfolio_snapshots_snapshot_date", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
