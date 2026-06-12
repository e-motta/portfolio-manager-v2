"""consolidate securities by symbol

Revision ID: 003
Revises: 002
Create Date: 2026-06-07
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "symbol_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_type_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_pct", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_type_id"], ["asset_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("securities") as batch_op:
        batch_op.add_column(
            sa.Column("purchase_price_usd", sa.Numeric(precision=18, scale=8), nullable=True)
        )
        batch_op.add_column(
            sa.Column("purchase_price_brl", sa.Numeric(precision=18, scale=8), nullable=True)
        )
        batch_op.add_column(
            sa.Column("provisional_fx", sa.Boolean(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("current_price_usd", sa.Numeric(precision=18, scale=8), nullable=True)
        )
        batch_op.add_column(
            sa.Column("current_price_brl", sa.Numeric(precision=18, scale=8), nullable=True)
        )

    op.execute(
        """
        UPDATE securities
        SET purchase_price_usd = latest_price,
            purchase_price_brl = price_brl,
            current_price_usd = latest_price,
            current_price_brl = price_brl,
            provisional_fx = 0
        """
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT asset_type_id, symbol, MAX(name) AS name, SUM(target_pct) AS target_pct
            FROM securities
            GROUP BY asset_type_id, symbol
            """
        )
    ).fetchall()

    for row in rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO symbol_targets
                (id, asset_type_id, symbol, name, target_pct, created_at, updated_at)
                VALUES (:id, :asset_type_id, :symbol, :name, :target_pct, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": uuid4(),
                "asset_type_id": row.asset_type_id,
                "symbol": row.symbol,
                "name": row.name or row.symbol,
                "target_pct": row.target_pct,
            },
        )

    with op.batch_alter_table("securities") as batch_op:
        batch_op.alter_column("purchase_price_usd", nullable=False)
        batch_op.alter_column("purchase_price_brl", nullable=False)
        batch_op.alter_column("provisional_fx", nullable=False)
        batch_op.alter_column("current_price_usd", nullable=False)
        batch_op.alter_column("current_price_brl", nullable=False)
        batch_op.drop_column("target_pct")
        batch_op.drop_column("latest_price")
        batch_op.drop_column("price_brl")


def downgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.add_column(
            sa.Column("latest_price", sa.Numeric(precision=18, scale=8), nullable=True)
        )
        batch_op.add_column(
            sa.Column("price_brl", sa.Numeric(precision=18, scale=8), nullable=True)
        )
        batch_op.add_column(
            sa.Column("target_pct", sa.Numeric(precision=5, scale=4), nullable=True)
        )

    op.execute(
        """
        UPDATE securities
        SET latest_price = current_price_usd,
            price_brl = current_price_brl,
            target_pct = 0
        """
    )

    with op.batch_alter_table("securities") as batch_op:
        batch_op.drop_column("current_price_brl")
        batch_op.drop_column("current_price_usd")
        batch_op.drop_column("provisional_fx")
        batch_op.drop_column("purchase_price_brl")
        batch_op.drop_column("purchase_price_usd")

    op.drop_table("symbol_targets")
