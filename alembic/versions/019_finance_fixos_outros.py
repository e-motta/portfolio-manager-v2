"""backfill Fixos and Outros expense categories

Revision ID: 019
Revises: 018
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlmodel import Session

    from app.services.finance_seed import seed_fixos_outros_if_missing

    bind = op.get_bind()
    with Session(bind) as session:
        seed_fixos_outros_if_missing(session)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        "DELETE FROM finance_expense_entries WHERE category IN ('Fixos', 'Outros')"
    )
