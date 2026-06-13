"""add cumbuca open finance fields

Revision ID: 020
Revises: 019
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlmodel
from alembic import op
import sqlalchemy as sa

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "cumbuca_refresh_token",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "cumbuca_access_token",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("cumbuca_token_expires_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "cumbuca_oauth_client_id",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "cumbuca_oauth_client_secret",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("cumbuca_connected_at", sa.DateTime(), nullable=True)
        )

    with op.batch_alter_table("finance_expense_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(
            sa.Column(
                "external_id",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )

    op.create_index(
        "ix_finance_expense_open_finance_external",
        "finance_expense_entries",
        ["user_id", "source", "external_id"],
        unique=True,
    )

    with op.batch_alter_table("investments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(
            sa.Column(
                "external_id",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )

    op.create_index(
        "ix_investments_open_finance_external",
        "investments",
        ["source", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_investments_open_finance_external", table_name="investments")
    op.drop_index(
        "ix_finance_expense_open_finance_external",
        table_name="finance_expense_entries",
    )

    with op.batch_alter_table("investments") as batch_op:
        batch_op.drop_column("external_id")
        batch_op.drop_column("source")

    with op.batch_alter_table("finance_expense_entries") as batch_op:
        batch_op.drop_column("external_id")
        batch_op.drop_column("source")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("cumbuca_connected_at")
        batch_op.drop_column("cumbuca_oauth_client_secret")
        batch_op.drop_column("cumbuca_oauth_client_id")
        batch_op.drop_column("cumbuca_token_expires_at")
        batch_op.drop_column("cumbuca_access_token")
        batch_op.drop_column("cumbuca_refresh_token")
