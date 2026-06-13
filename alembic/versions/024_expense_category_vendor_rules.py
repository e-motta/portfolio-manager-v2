"""reapply expense category vendor rules

Revision ID: 024
Revises: 023
Create Date: 2026-06-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlmodel import Session

    from app.services.finance import migrate_expense_categories

    bind = op.get_bind()
    with Session(bind) as session:
        migrate_expense_categories(session)


def downgrade() -> None:
    pass
