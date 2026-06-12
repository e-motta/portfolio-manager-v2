"""add users and portfolio ownership

Revision ID: 015
Revises: 014
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("google_sub", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("picture_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)

    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_portfolios_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.add_column(sa.Column("portfolio_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_portfolio_snapshots_portfolio_id_portfolios",
            "portfolios",
            ["portfolio_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.execute(
        sa.text(
            """
            UPDATE portfolio_snapshots
            SET portfolio_id = (SELECT id FROM portfolios ORDER BY created_at LIMIT 1)
            WHERE portfolio_id IS NULL
            """
        )
    )

    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.drop_index("ix_portfolio_snapshots_snapshot_date")
        batch_op.create_index(
            "ix_portfolio_snapshots_portfolio_id_snapshot_date",
            ["portfolio_id", "snapshot_date"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.drop_index("ix_portfolio_snapshots_portfolio_id_snapshot_date")
        batch_op.create_index(
            "ix_portfolio_snapshots_snapshot_date",
            ["snapshot_date"],
            unique=True,
        )
        batch_op.drop_constraint(
            "fk_portfolio_snapshots_portfolio_id_portfolios",
            type_="foreignkey",
        )
        batch_op.drop_column("portfolio_id")

    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.drop_constraint("fk_portfolios_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")

    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
