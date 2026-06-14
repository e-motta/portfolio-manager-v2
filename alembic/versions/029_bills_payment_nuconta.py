"""set bills expense payment account to Nuconta

Revision ID: 029
Revises: 028
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE finance_expense_entries "
            "SET payment_account = 'Nuconta' "
            "WHERE category = 'Bills'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE finance_expense_entries "
            "SET payment_account = 'Manual' "
            "WHERE category = 'Bills' AND payment_account = 'Nuconta'"
        )
    )
