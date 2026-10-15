"""Migration 041 disconnects tokenless Cumbuca rows and clears connected_at."""

from sqlalchemy import text
from sqlmodel import select

from app.models.open_finance import OpenFinanceConnection
from app.models.user import User


_DISCONNECT_SQL = """
UPDATE open_finance_connections
SET status = 'disconnected'
WHERE provider = 'cumbuca'
  AND refresh_token IS NULL
  AND access_token IS NULL
"""

_CLEAR_CONNECTED_AT_SQL = """
UPDATE users
SET cumbuca_connected_at = NULL
WHERE cumbuca_refresh_token IS NULL
"""


def test_migration_041_disconnects_tokenless_cumbuca_and_clears_connected_at(session):
    user = session.exec(select(User)).one()
    user.cumbuca_oauth_client_id = "keep-client"
    user.cumbuca_connected_at = user.created_at
    user.cumbuca_refresh_token = None
    session.add(user)
    connection = OpenFinanceConnection(
        user_id=user.id,
        provider="cumbuca",
        external_id="",
        institution_name="Cumbuca Open Finance",
        status="active",
        oauth_client_id="keep-client",
        refresh_token=None,
        access_token=None,
    )
    session.add(connection)
    session.commit()
    connection_id = str(connection.id)

    session.exec(text(_DISCONNECT_SQL))
    session.exec(text(_CLEAR_CONNECTED_AT_SQL))
    session.commit()

    stored = session.get(OpenFinanceConnection, connection.id)
    assert stored is not None
    assert stored.status == "disconnected"
    assert stored.oauth_client_id == "keep-client"
    session.refresh(user)
    assert user.cumbuca_connected_at is None
    assert user.cumbuca_oauth_client_id == "keep-client"
    assert connection_id == str(stored.id)
