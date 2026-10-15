"""add unique (user_id, external_id) constraints for finance tables

Revision ID: 039
Revises: 038
Create Date: 2026-10-15

This migration adds unique constraints on (user_id, external_id) to:
- finance_expense_entries
- finance_income_entries
- finance_transfer_entries

This prevents duplicate imports from Open Finance providers. NULL external_id
values are allowed since they represent manual entries; both Postgres and
SQLite treat NULL as unique in unique constraints.

Before adding constraints, this migration removes duplicate entries (keeping
the earliest one by created_at) to ensure the migration succeeds.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _deduplicate_table(bind, table_name: str, dialect: str) -> None:
    """Remove duplicate rows with the same (user_id, external_id) keeping the earliest."""
    if dialect == "sqlite":
        bind.execute(
            sa.text(f"""
                DELETE FROM {table_name}
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM {table_name}
                    WHERE external_id IS NOT NULL
                    GROUP BY user_id, external_id
                )
                AND external_id IS NOT NULL
            """)
        )
    else:
        bind.execute(
            sa.text(f"""
                DELETE FROM {table_name} t1
                USING {table_name} t2
                WHERE t1.external_id IS NOT NULL
                  AND t2.external_id IS NOT NULL
                  AND t1.user_id = t2.user_id
                  AND t1.external_id = t2.external_id
                  AND t1.created_at > t2.created_at
            """)
        )
        bind.execute(
            sa.text(f"""
                DELETE FROM {table_name} t1
                USING {table_name} t2
                WHERE t1.external_id IS NOT NULL
                  AND t2.external_id IS NOT NULL
                  AND t1.user_id = t2.user_id
                  AND t1.external_id = t2.external_id
                  AND t1.created_at = t2.created_at
                  AND t1.id > t2.id
            """)
        )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    _deduplicate_table(bind, "finance_expense_entries", dialect)
    _deduplicate_table(bind, "finance_income_entries", dialect)
    _deduplicate_table(bind, "finance_transfer_entries", dialect)

    if dialect == "sqlite":
        with op.batch_alter_table("finance_expense_entries") as batch_op:
            batch_op.create_unique_constraint(
                "uq_expense_user_external_id",
                ["user_id", "external_id"],
            )
        with op.batch_alter_table("finance_income_entries") as batch_op:
            batch_op.create_unique_constraint(
                "uq_income_user_external_id",
                ["user_id", "external_id"],
            )
        with op.batch_alter_table("finance_transfer_entries") as batch_op:
            batch_op.create_unique_constraint(
                "uq_transfer_user_external_id",
                ["user_id", "external_id"],
            )
    else:
        op.create_unique_constraint(
            "uq_expense_user_external_id",
            "finance_expense_entries",
            ["user_id", "external_id"],
        )
        op.create_unique_constraint(
            "uq_income_user_external_id",
            "finance_income_entries",
            ["user_id", "external_id"],
        )
        op.create_unique_constraint(
            "uq_transfer_user_external_id",
            "finance_transfer_entries",
            ["user_id", "external_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("finance_transfer_entries") as batch_op:
            batch_op.drop_constraint("uq_transfer_user_external_id", type_="unique")
        with op.batch_alter_table("finance_income_entries") as batch_op:
            batch_op.drop_constraint("uq_income_user_external_id", type_="unique")
        with op.batch_alter_table("finance_expense_entries") as batch_op:
            batch_op.drop_constraint("uq_expense_user_external_id", type_="unique")
    else:
        op.drop_constraint("uq_transfer_user_external_id", "finance_transfer_entries", type_="unique")
        op.drop_constraint("uq_income_user_external_id", "finance_income_entries", type_="unique")
        op.drop_constraint("uq_expense_user_external_id", "finance_expense_entries", type_="unique")
