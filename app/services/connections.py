"""Unified Open Finance connections service.

Manages connections from multiple providers (Cumbuca, Pluggy) through
the OpenFinanceConnection model.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.models.open_finance import OpenFinanceConnection
from app.models.user import User

PROVIDER_CUMBUCA = "cumbuca"
PROVIDER_PLUGGY = "pluggy"


def get_all_connections(session: Session, user_id: UUID) -> list[OpenFinanceConnection]:
    """Get all Open Finance connections for a user."""
    return list(
        session.exec(
            select(OpenFinanceConnection)
            .where(OpenFinanceConnection.user_id == user_id)
            .order_by(OpenFinanceConnection.provider, OpenFinanceConnection.institution_name)
        ).all()
    )


def get_active_connections(session: Session, user_id: UUID) -> list[OpenFinanceConnection]:
    """Get active Open Finance connections for a user."""
    return list(
        session.exec(
            select(OpenFinanceConnection)
            .where(OpenFinanceConnection.user_id == user_id)
            .where(OpenFinanceConnection.status == "active")
            .order_by(OpenFinanceConnection.provider, OpenFinanceConnection.institution_name)
        ).all()
    )


def get_connections_by_provider(
    session: Session,
    user_id: UUID,
    provider: str,
) -> list[OpenFinanceConnection]:
    """Get connections for a specific provider."""
    return list(
        session.exec(
            select(OpenFinanceConnection)
            .where(OpenFinanceConnection.user_id == user_id)
            .where(OpenFinanceConnection.provider == provider)
            .order_by(OpenFinanceConnection.institution_name)
        ).all()
    )


def get_cumbuca_connection(session: Session, user_id: UUID) -> OpenFinanceConnection | None:
    """Get the Cumbuca connection for a user (at most one per user)."""
    return session.exec(
        select(OpenFinanceConnection)
        .where(OpenFinanceConnection.user_id == user_id)
        .where(OpenFinanceConnection.provider == PROVIDER_CUMBUCA)
    ).first()


def get_cumbuca_connection_or_from_user(
    session: Session,
    user: User,
) -> OpenFinanceConnection | None:
    """Get Cumbuca connection, falling back to user columns for backward compatibility.

    During migration, data may be in either location. This provides a unified view.
    """
    connection = get_cumbuca_connection(session, user.id)
    if connection:
        return connection

    if user.cumbuca_refresh_token:
        return OpenFinanceConnection(
            id=user.id,
            user_id=user.id,
            provider=PROVIDER_CUMBUCA,
            external_id="",
            institution_name="Cumbuca Open Finance",
            status="active",
            oauth_client_id=user.cumbuca_oauth_client_id,
            oauth_client_secret=user.cumbuca_oauth_client_secret,
            refresh_token=user.cumbuca_refresh_token,
            access_token=user.cumbuca_access_token,
            token_expires_at=user.cumbuca_token_expires_at,
            last_synced_at=user.cumbuca_connected_at,
            created_at=user.cumbuca_connected_at or user.created_at,
            updated_at=user.cumbuca_connected_at or user.created_at,
        )

    return None


def cumbuca_connection_is_live(connection: OpenFinanceConnection) -> bool:
    """A Cumbuca row is live only when it is active and has a refresh token."""
    return connection.status == "active" and bool(connection.refresh_token)


def public_connection_status(connection: OpenFinanceConnection) -> str:
    """Status shown to clients. Tokenless Cumbuca rows are never reported as active."""
    if connection.provider == PROVIDER_CUMBUCA and not connection.refresh_token:
        if connection.status == "active":
            return "pending"
        return connection.status
    return connection.status


def user_has_cumbuca_connection(session: Session, user: User) -> bool:
    """Check if user has an active Cumbuca connection (in either location)."""
    connection = get_cumbuca_connection(session, user.id)
    if connection:
        return cumbuca_connection_is_live(connection)
    return bool(user.cumbuca_refresh_token)


def create_or_update_cumbuca_connection(
    session: Session,
    user: User,
    *,
    oauth_client_id: str,
    oauth_client_secret: str,
    refresh_token: str | None = None,
    access_token: str | None = None,
    token_expires_at: datetime | None = None,
) -> OpenFinanceConnection:
    """Create or update a Cumbuca connection."""
    connection = get_cumbuca_connection(session, user.id)

    if not connection:
        connection = OpenFinanceConnection(
            user_id=user.id,
            provider=PROVIDER_CUMBUCA,
            external_id="",
            institution_name="Cumbuca Open Finance",
            status="pending",
        )

    connection.oauth_client_id = oauth_client_id
    connection.oauth_client_secret = oauth_client_secret
    if refresh_token is None and not connection.refresh_token:
        refresh_token = user.cumbuca_refresh_token
    if access_token is None and not connection.access_token:
        access_token = user.cumbuca_access_token
    if token_expires_at is None and not connection.token_expires_at:
        token_expires_at = user.cumbuca_token_expires_at
    if refresh_token is not None:
        connection.refresh_token = refresh_token
    if access_token is not None:
        connection.access_token = access_token
    if token_expires_at is not None:
        connection.token_expires_at = token_expires_at
    has_tokens = bool(connection.refresh_token or connection.access_token)
    connection.status = "active" if has_tokens else "pending"
    connection.updated_at = datetime.utcnow()

    session.add(connection)
    session.commit()
    session.refresh(connection)

    user.cumbuca_oauth_client_id = oauth_client_id
    user.cumbuca_oauth_client_secret = oauth_client_secret
    if refresh_token is not None:
        user.cumbuca_refresh_token = refresh_token
    if access_token is not None:
        user.cumbuca_access_token = access_token
    if token_expires_at is not None:
        user.cumbuca_token_expires_at = token_expires_at
    if has_tokens:
        user.cumbuca_connected_at = connection.updated_at
    session.add(user)
    session.commit()

    return connection


def update_cumbuca_tokens(
    session: Session,
    user: User,
    connection: OpenFinanceConnection,
    *,
    refresh_token: str | None = None,
    access_token: str | None = None,
    expires_in: int | None = None,
) -> None:
    """Update Cumbuca tokens on both connection and user (for backward compatibility)."""
    now = datetime.now(timezone.utc)

    if refresh_token:
        connection.refresh_token = refresh_token
        user.cumbuca_refresh_token = refresh_token
    if access_token:
        connection.access_token = access_token
        user.cumbuca_access_token = access_token
    if expires_in:
        expires_at = now + timedelta(seconds=expires_in)
        connection.token_expires_at = expires_at
        user.cumbuca_token_expires_at = expires_at

    if refresh_token or access_token:
        connection.status = "active"
    connection.updated_at = now
    user.cumbuca_connected_at = now

    session.add(connection)
    session.add(user)
    session.commit()


def disconnect_cumbuca_connection(session: Session, user: User) -> None:
    """Disconnect Cumbuca by clearing tokens/secret and marking the row disconnected."""
    connection = get_cumbuca_connection(session, user.id)
    if connection:
        connection.refresh_token = None
        connection.access_token = None
        connection.token_expires_at = None
        connection.oauth_client_secret = None
        connection.status = "disconnected"
        connection.updated_at = datetime.now(timezone.utc)
        session.add(connection)

    user.cumbuca_refresh_token = None
    user.cumbuca_access_token = None
    user.cumbuca_token_expires_at = None
    user.cumbuca_connected_at = None
    session.add(user)
    session.commit()


def get_connection_by_id(
    session: Session,
    user_id: UUID,
    connection_id: UUID,
) -> OpenFinanceConnection | None:
    """Get a connection by ID, ensuring it belongs to the user."""
    return session.exec(
        select(OpenFinanceConnection)
        .where(OpenFinanceConnection.id == connection_id)
        .where(OpenFinanceConnection.user_id == user_id)
    ).first()


def delete_connection(session: Session, connection: OpenFinanceConnection) -> None:
    """Delete a connection."""
    session.delete(connection)
    session.commit()


def _connection_payload(conn: OpenFinanceConnection) -> dict:
    return {
        "id": str(conn.id),
        "provider": conn.provider,
        "external_id": conn.external_id,
        "institution_name": conn.institution_name,
        "status": public_connection_status(conn),
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
    }


def connections_summary(connections: list[OpenFinanceConnection]) -> dict:
    """Generate a summary of connections for API responses."""
    by_provider: dict[str, list[dict]] = {}

    for conn in connections:
        by_provider.setdefault(conn.provider, []).append(_connection_payload(conn))

    return {
        "connections": [_connection_payload(conn) for conn in connections],
        "by_provider": by_provider,
        "has_cumbuca": any(
            c.provider == PROVIDER_CUMBUCA and cumbuca_connection_is_live(c)
            for c in connections
        ),
        "has_pluggy": any(
            c.provider == PROVIDER_PLUGGY and c.status not in {"disconnected", "inactive"}
            for c in connections
        ),
        "total_count": len(connections),
    }
