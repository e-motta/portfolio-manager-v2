"""seed finance data from synthetic placeholder

Revision ID: 018
Revises: 017
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    user_ids = bind.execute(sa.text("SELECT id FROM users")).fetchall()
    if not user_ids:
        return

    from sqlmodel import Session

    from app.services.finance_seed import seed_finance_data

    with Session(bind) as session:
        seed_finance_data(session, UUID(str(user_ids[0][0])))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM finance_summary_amounts"))
    bind.execute(sa.text("DELETE FROM finance_expense_entries"))
    bind.execute(sa.text("DELETE FROM finance_income_entries"))
