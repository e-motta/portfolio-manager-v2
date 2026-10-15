"""add open_finance_connections table and migrate cumbuca data

Revision ID: 038
Revises: 037
Create Date: 2026-10-15

This migration:
1. Creates the open_finance_connections table to support multiple providers
2. Migrates existing Cumbuca token data from users table
3. Keeps the cumbuca_* columns on users for backward compatibility during transition
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlmodel
from alembic import op
import sqlalchemy as sa

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "open_finance_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("institution_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("institution_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("oauth_client_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("oauth_client_secret", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("refresh_token", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("access_token", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("item_access_token", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "external_id", name="uq_connection_identity"),
    )
    op.create_index("ix_open_finance_connections_provider", "open_finance_connections", ["provider"])
    op.create_index("ix_open_finance_connections_status", "open_finance_connections", ["status"])
    op.create_index("ix_open_finance_connections_user_id", "open_finance_connections", ["user_id"])
    op.create_index("ix_open_finance_connections_external_id", "open_finance_connections", ["external_id"])

    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        bind.execute(
            sa.text("""
                INSERT INTO open_finance_connections (
                    id, user_id, provider, external_id, institution_name, status,
                    oauth_client_id, oauth_client_secret, refresh_token, access_token,
                    token_expires_at, last_synced_at, created_at, updated_at
                )
                SELECT
                    lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' ||
                          substr(hex(randomblob(2)),2) || '-' ||
                          substr('89ab', abs(random()) % 4 + 1, 1) ||
                          substr(hex(randomblob(2)), 2) || '-' || hex(randomblob(6))),
                    id,
                    'cumbuca',
                    '',
                    'Cumbuca Open Finance',
                    'active',
                    cumbuca_oauth_client_id,
                    cumbuca_oauth_client_secret,
                    cumbuca_refresh_token,
                    cumbuca_access_token,
                    cumbuca_token_expires_at,
                    cumbuca_connected_at,
                    COALESCE(cumbuca_connected_at, created_at),
                    COALESCE(cumbuca_connected_at, created_at)
                FROM users
                WHERE cumbuca_refresh_token IS NOT NULL
            """)
        )
    else:
        bind.execute(
            sa.text("""
                INSERT INTO open_finance_connections (
                    id, user_id, provider, external_id, institution_name, status,
                    oauth_client_id, oauth_client_secret, refresh_token, access_token,
                    token_expires_at, last_synced_at, created_at, updated_at
                )
                SELECT
                    gen_random_uuid(),
                    id,
                    'cumbuca',
                    '',
                    'Cumbuca Open Finance',
                    'active',
                    cumbuca_oauth_client_id,
                    cumbuca_oauth_client_secret,
                    cumbuca_refresh_token,
                    cumbuca_access_token,
                    cumbuca_token_expires_at,
                    cumbuca_connected_at,
                    COALESCE(cumbuca_connected_at, created_at),
                    COALESCE(cumbuca_connected_at, created_at)
                FROM users
                WHERE cumbuca_refresh_token IS NOT NULL
            """)
        )


def downgrade() -> None:
    op.drop_index("ix_open_finance_connections_external_id", table_name="open_finance_connections")
    op.drop_index("ix_open_finance_connections_user_id", table_name="open_finance_connections")
    op.drop_index("ix_open_finance_connections_status", table_name="open_finance_connections")
    op.drop_index("ix_open_finance_connections_provider", table_name="open_finance_connections")
    op.drop_table("open_finance_connections")
