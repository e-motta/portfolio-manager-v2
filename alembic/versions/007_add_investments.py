"""add investments table

Revision ID: 007
Revises: 006
Create Date: 2026-06-07
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_type_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("original_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("market_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_type_id"], ["asset_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, name, current_value
            FROM asset_types
            WHERE is_exchange_traded = 0 AND current_value > 0
            """
        )
    ).fetchall()

    for row in rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO investments
                (id, asset_type_id, name, original_value, market_value, created_at, updated_at)
                VALUES (:id, :asset_type_id, :name, :original_value, :market_value, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": uuid4(),
                "asset_type_id": row.id,
                "name": f"{row.name} balance",
                "original_value": row.current_value,
                "market_value": row.current_value,
            },
        )


def downgrade() -> None:
    op.drop_table("investments")
