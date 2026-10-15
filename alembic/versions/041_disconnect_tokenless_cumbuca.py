"""disconnect tokenless cumbuca rows

Revision ID: 041
Revises: 040
Create Date: 2026-10-15

Abandoned Cumbuca OAuth left open_finance_connections rows with
status='active' and no tokens, which made the Open Finance page treat
Cumbuca as connected. Mark those rows disconnected and clear
users.cumbuca_connected_at when there is no refresh token. Keep the
OAuth client id so reconnect can reuse it.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE open_finance_connections
            SET status = 'disconnected'
            WHERE provider = 'cumbuca'
              AND refresh_token IS NULL
              AND access_token IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE users
            SET cumbuca_connected_at = NULL
            WHERE cumbuca_refresh_token IS NULL
            """
        )
    )


def downgrade() -> None:
    pass
