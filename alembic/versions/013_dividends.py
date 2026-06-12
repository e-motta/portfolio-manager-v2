"""dividend tracking

Revision ID: 013
Revises: 012
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dividends",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_type_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("gross_amount_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("withholding_tax_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("net_amount_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("import_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_type_id"], ["asset_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_type_id", "import_key", name="uq_dividend_asset_import_key"),
    )
    op.create_index(op.f("ix_dividends_symbol"), "dividends", ["symbol"], unique=False)
    op.create_index(op.f("ix_dividends_source"), "dividends", ["source"], unique=False)
    op.create_index(op.f("ix_dividends_import_key"), "dividends", ["import_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dividends_import_key"), table_name="dividends")
    op.drop_index(op.f("ix_dividends_source"), table_name="dividends")
    op.drop_index(op.f("ix_dividends_symbol"), table_name="dividends")
    op.drop_table("dividends")
