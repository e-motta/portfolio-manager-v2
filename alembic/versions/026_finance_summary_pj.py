"""merge pro labore and lucro summary lines into PJ

Revision ID: 026
Revises: 025
Create Date: 2026-06-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlmodel import Session

    from app.services.finance import migrate_pro_labore_lucro_to_pj

    bind = op.get_bind()
    with Session(bind) as session:
        migrate_pro_labore_lucro_to_pj(session)


def downgrade() -> None:
    pass
