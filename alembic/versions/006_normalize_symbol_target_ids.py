"""normalize symbol target primary keys to canonical uuid text

Revision ID: 006
Revises: 005
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id FROM symbol_targets WHERE id LIKE '%-%'")
    ).fetchall()

    for row in rows:
        old_id = row.id
        new_id = old_id.replace("-", "")
        connection.execute(
            sa.text("UPDATE symbol_targets SET id = :new_id WHERE id = :old_id"),
            {"old_id": old_id, "new_id": new_id},
        )


def downgrade() -> None:
    pass
