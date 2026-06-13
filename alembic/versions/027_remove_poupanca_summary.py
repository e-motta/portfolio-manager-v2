"""remove poupanca summary lines; income tab totals flow to Outros

Revision ID: 027
Revises: 026
Create Date: 2026-06-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlmodel import Session

    from app.services.finance import remove_poupanca_summary_lines

    bind = op.get_bind()
    with Session(bind) as session:
        remove_poupanca_summary_lines(session)


def downgrade() -> None:
    pass
