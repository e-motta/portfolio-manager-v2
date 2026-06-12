"""optional asset type target weights

Revision ID: 012
Revises: 011
Create Date: 2026-06-08
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("asset_types") as batch_op:
        batch_op.alter_column("target_pct", nullable=True)

    with op.batch_alter_table("snapshot_asset_classes") as batch_op:
        batch_op.alter_column("target_weight", nullable=True)


def downgrade() -> None:
    op.execute("UPDATE asset_types SET target_pct = 0 WHERE target_pct IS NULL")
    op.execute(
        "UPDATE snapshot_asset_classes SET target_weight = 0 WHERE target_weight IS NULL"
    )

    with op.batch_alter_table("asset_types") as batch_op:
        batch_op.alter_column("target_pct", nullable=False)

    with op.batch_alter_table("snapshot_asset_classes") as batch_op:
        batch_op.alter_column("target_weight", nullable=False)
