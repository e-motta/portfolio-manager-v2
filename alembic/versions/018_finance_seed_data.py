"""finance seed migration placeholder

Revision ID: 018
Revises: 017
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM finance_summary_amounts"))
    bind.execute(sa.text("DELETE FROM finance_expense_entries"))
    bind.execute(sa.text("DELETE FROM finance_income_entries"))
