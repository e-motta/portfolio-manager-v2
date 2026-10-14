"""normalize index names to match model definitions

Revision ID: 037
Revises: 036
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_indexes(inspector, table_name: str) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes(table_name) if idx["name"]}


def _get_existing_constraints(inspector, table_name: str) -> set[str]:
    return {c["name"] for c in inspector.get_unique_constraints(table_name) if c["name"]}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    expense_indexes = _get_existing_indexes(inspector, "finance_expense_entries")
    if "ix_finance_expense_open_finance_external" in expense_indexes:
        op.drop_index(
            "ix_finance_expense_open_finance_external",
            table_name="finance_expense_entries",
        )
    if "ix_finance_expense_entries_external_id" not in expense_indexes:
        op.create_index(
            "ix_finance_expense_entries_external_id",
            "finance_expense_entries",
            ["external_id"],
        )
    if "ix_finance_expense_entries_source" not in expense_indexes:
        op.create_index(
            "ix_finance_expense_entries_source",
            "finance_expense_entries",
            ["source"],
        )

    income_indexes = _get_existing_indexes(inspector, "finance_income_entries")
    if "ix_finance_income_open_finance_external" in income_indexes:
        op.drop_index(
            "ix_finance_income_open_finance_external",
            table_name="finance_income_entries",
        )
    if "ix_finance_income_entries_external_id" not in income_indexes:
        op.create_index(
            "ix_finance_income_entries_external_id",
            "finance_income_entries",
            ["external_id"],
        )
    if "ix_finance_income_entries_source" not in income_indexes:
        op.create_index(
            "ix_finance_income_entries_source",
            "finance_income_entries",
            ["source"],
        )

    investment_indexes = _get_existing_indexes(inspector, "investments")
    if "ix_investments_open_finance_external" in investment_indexes:
        op.drop_index(
            "ix_investments_open_finance_external",
            table_name="investments",
        )
    if "ix_investments_external_id" not in investment_indexes:
        op.create_index(
            "ix_investments_external_id",
            "investments",
            ["external_id"],
        )
    if "ix_investments_source" not in investment_indexes:
        op.create_index(
            "ix_investments_source",
            "investments",
            ["source"],
        )

    snapshot_indexes = _get_existing_indexes(inspector, "portfolio_snapshots")
    snapshot_constraints = _get_existing_constraints(inspector, "portfolio_snapshots")
    dialect = bind.dialect.name

    if "ix_portfolio_snapshots_portfolio_id_snapshot_date" in snapshot_indexes:
        op.drop_index(
            "ix_portfolio_snapshots_portfolio_id_snapshot_date",
            table_name="portfolio_snapshots",
        )

    if dialect == "sqlite":
        pass
    else:
        if "portfolio_snapshots_snapshot_date_key" in snapshot_constraints:
            op.drop_constraint(
                "portfolio_snapshots_snapshot_date_key",
                "portfolio_snapshots",
                type_="unique",
            )
        existing_constraints_after = _get_existing_constraints(
            inspect(op.get_bind()), "portfolio_snapshots"
        )
        has_composite_constraint = any(
            "portfolio_id" in str(c) and "snapshot_date" in str(c)
            for c in existing_constraints_after
        )
        if not has_composite_constraint:
            op.create_unique_constraint(
                "uq_portfolio_snapshots_portfolio_date",
                "portfolio_snapshots",
                ["portfolio_id", "snapshot_date"],
            )

    securities_indexes = _get_existing_indexes(inspector, "securities")
    if "ix_securities_symbol" not in securities_indexes:
        op.create_index(
            "ix_securities_symbol",
            "securities",
            ["symbol"],
        )

    symbol_target_indexes = _get_existing_indexes(inspector, "symbol_targets")
    if "ix_symbol_targets_symbol" not in symbol_target_indexes:
        op.create_index(
            "ix_symbol_targets_symbol",
            "symbol_targets",
            ["symbol"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    dialect = bind.dialect.name

    symbol_target_indexes = _get_existing_indexes(inspector, "symbol_targets")
    if "ix_symbol_targets_symbol" in symbol_target_indexes:
        op.drop_index("ix_symbol_targets_symbol", table_name="symbol_targets")

    securities_indexes = _get_existing_indexes(inspector, "securities")
    if "ix_securities_symbol" in securities_indexes:
        op.drop_index("ix_securities_symbol", table_name="securities")

    if dialect != "sqlite":
        snapshot_constraints = _get_existing_constraints(inspector, "portfolio_snapshots")
        if "uq_portfolio_snapshots_portfolio_date" in snapshot_constraints:
            op.drop_constraint(
                "uq_portfolio_snapshots_portfolio_date",
                "portfolio_snapshots",
                type_="unique",
            )
        op.create_unique_constraint(
            "portfolio_snapshots_snapshot_date_key",
            "portfolio_snapshots",
            ["snapshot_date"],
        )
    op.create_index(
        "ix_portfolio_snapshots_portfolio_id_snapshot_date",
        "portfolio_snapshots",
        ["portfolio_id", "snapshot_date"],
        unique=True,
    )

    investment_indexes = _get_existing_indexes(inspector, "investments")
    if "ix_investments_source" in investment_indexes:
        op.drop_index("ix_investments_source", table_name="investments")
    if "ix_investments_external_id" in investment_indexes:
        op.drop_index("ix_investments_external_id", table_name="investments")
    op.create_index(
        "ix_investments_open_finance_external",
        "investments",
        ["source", "external_id"],
        unique=True,
    )

    income_indexes = _get_existing_indexes(inspector, "finance_income_entries")
    if "ix_finance_income_entries_source" in income_indexes:
        op.drop_index("ix_finance_income_entries_source", table_name="finance_income_entries")
    if "ix_finance_income_entries_external_id" in income_indexes:
        op.drop_index("ix_finance_income_entries_external_id", table_name="finance_income_entries")
    op.create_index(
        "ix_finance_income_open_finance_external",
        "finance_income_entries",
        ["user_id", "source", "external_id"],
        unique=True,
    )

    expense_indexes = _get_existing_indexes(inspector, "finance_expense_entries")
    if "ix_finance_expense_entries_source" in expense_indexes:
        op.drop_index("ix_finance_expense_entries_source", table_name="finance_expense_entries")
    if "ix_finance_expense_entries_external_id" in expense_indexes:
        op.drop_index("ix_finance_expense_entries_external_id", table_name="finance_expense_entries")
    op.create_index(
        "ix_finance_expense_open_finance_external",
        "finance_expense_entries",
        ["user_id", "source", "external_id"],
        unique=True,
    )
