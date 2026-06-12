"""dedupe symbol targets and enforce one target per ticker

Revision ID: 005
Revises: 004
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = connection.execute(
        sa.text(
            """
            SELECT asset_type_id, symbol, MIN(id) AS keep_id
            FROM symbol_targets
            GROUP BY asset_type_id, symbol
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    for row in duplicates:
        connection.execute(
            sa.text(
                """
                DELETE FROM symbol_targets
                WHERE asset_type_id = :asset_type_id
                  AND symbol = :symbol
                  AND id != :keep_id
                """
            ),
            {
                "asset_type_id": row.asset_type_id,
                "symbol": row.symbol,
                "keep_id": row.keep_id,
            },
        )

    with op.batch_alter_table("symbol_targets") as batch_op:
        batch_op.create_unique_constraint(
            "uq_symbol_target_asset_symbol",
            ["asset_type_id", "symbol"],
        )


def downgrade() -> None:
    with op.batch_alter_table("symbol_targets") as batch_op:
        batch_op.drop_constraint("uq_symbol_target_asset_symbol", type_="unique")
