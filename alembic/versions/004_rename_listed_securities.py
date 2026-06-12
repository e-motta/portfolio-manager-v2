"""rename exchange traded asset class label

Revision ID: 004
Revises: 003
Create Date: 2026-06-07
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE asset_types SET name = 'Listed Securities' "
        "WHERE slug = 'exchange-traded'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE asset_types SET name = 'Exchange Traded' "
        "WHERE slug = 'exchange-traded'"
    )
