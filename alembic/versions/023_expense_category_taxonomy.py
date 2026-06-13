"""migrate expense categories to expanded taxonomy

Revision ID: 023
Revises: 022
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlmodel import Session

    from app.services.finance import migrate_expense_categories

    bind = op.get_bind()
    with Session(bind) as session:
        migrate_expense_categories(session)


def downgrade() -> None:
    bind = op.get_bind()
    reverse_map = {
        "Alimentação fora": "Restaurante + entrega",
        "Lanche e café": "Lanche/janta",
        "Supermercado": "Supermercado + online",
        "Bar e lazer": "Bar + bebidas",
        "Transporte": "Uber",
        "Assinaturas digitais": "Fixos",
        "Academia e treino": "Fixos",
        "Telecom": "Fixos",
        "Seguros": "Fixos",
        "Contabilidade / PJ": "Fixos",
        "Corrida": "Outros",
        "Saúde": "Outros",
        "Casa": "Outros",
        "Compras online": "Supermercado + online",
        "Presentes": "Outros",
        "Profissional": "Outros",
    }
    for new_category, old_category in reverse_map.items():
        bind.execute(
            sa.text(
                "UPDATE finance_expense_entries SET category = :old "
                "WHERE category = :new"
            ),
            {"old": old_category, "new": new_category},
        )
        bind.execute(
            sa.text(
                "UPDATE finance_vendor_categories SET category = :old "
                "WHERE category = :new"
            ),
            {"old": old_category, "new": new_category},
        )
