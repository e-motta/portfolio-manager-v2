"""clear legacy manual values on non-listed asset classes

Revision ID: 008
Revises: 007
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE asset_types
            SET current_value = 0
            WHERE is_exchange_traded = 0
            """
        )
    )


def downgrade() -> None:
    pass
