"""fix cumbuca connections last_synced_at

Revision ID: 040
Revises: 039
Create Date: 2026-10-15

Migration 038 incorrectly set last_synced_at to cumbuca_connected_at for
existing Cumbuca connections. last_synced_at should only be set when data
is actually synced, not when the connection was established.

This corrective migration sets last_synced_at to NULL for Cumbuca connections
where it was incorrectly set.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("""
            UPDATE open_finance_connections
            SET last_synced_at = NULL
            WHERE provider = 'cumbuca'
              AND last_synced_at IS NOT NULL
        """)
    )


def downgrade() -> None:
    pass
