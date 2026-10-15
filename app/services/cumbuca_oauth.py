import base64
import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlmodel import Session

from app.core.config import settings
from app.models.open_finance import OpenFinanceConnection
from app.models.user import User
from app.services.connections import (
    create_or_update_cumbuca_connection,
    get_cumbuca_connection,
    update_cumbuca_tokens,
)

OAUTH_PURPOSE_CUMBUCA = "cumbuca"
OPEN_FINANCE_SOURCE = "open_finance"


def user_has_cumbuca(user: User) -> bool:
    """Check if user has Cumbuca connection (via user columns, for backward compat)."""
    return bool(user.cumbuca_refresh_token)


def _pkce_pair() -> tuple[str, str]:
    verifier = "".join(
        secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(64)
    )
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def _registration_url() -> str:
    return f"{settings.CUMBUCA_AUTH_SERVER}/clients-registrations/openid-connect"


def _token_url() -> str:
    return f"{settings.CUMBUCA_AUTH_SERVER}/protocol/openid-connect/token"


def _authorization_url() -> str:
    return f"{settings.CUMBUCA_AUTH_SERVER}/protocol/openid-connect/auth"


def _revocation_url() -> str:
    return f"{settings.CUMBUCA_AUTH_SERVER}/protocol/openid-connect/revoke"


def ensure_oauth_client(session: Session, user: User) -> tuple[str, str]:
    """Ensure OAuth client credentials exist, creating them if needed.

    Returns (client_id, client_secret). Stores credentials in both the
    connections table (source of truth) and user columns (backward compat).
    """
    connection = get_cumbuca_connection(session, user.id)
    if connection and connection.oauth_client_id and connection.oauth_client_secret:
        if not user.cumbuca_oauth_client_id:
            user.cumbuca_oauth_client_id = connection.oauth_client_id
            user.cumbuca_oauth_client_secret = connection.oauth_client_secret
            session.add(user)
            session.commit()
        return connection.oauth_client_id, connection.oauth_client_secret

    if user.cumbuca_oauth_client_id and user.cumbuca_oauth_client_secret:
        create_or_update_cumbuca_connection(
            session,
            user,
            oauth_client_id=user.cumbuca_oauth_client_id,
            oauth_client_secret=user.cumbuca_oauth_client_secret,
        )
        return user.cumbuca_oauth_client_id, user.cumbuca_oauth_client_secret

    payload = {
        "client_name": "Portfolio Manager",
        "redirect_uris": [settings.CUMBUCA_REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_basic",
    }
    response = httpx.post(_registration_url(), json=payload, timeout=30.0)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="Could not register Open Finance OAuth client.",
        )
    data = response.json()
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=502,
            detail="Open Finance OAuth registration returned incomplete data.",
        )

    create_or_update_cumbuca_connection(
        session,
        user,
        oauth_client_id=client_id,
        oauth_client_secret=client_secret,
    )

    return client_id, client_secret


def build_authorization_request(session: Session, user: User) -> tuple[str, str, str]:
    client_id, _ = ensure_oauth_client(session, user)
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": settings.CUMBUCA_REDIRECT_URI,
        "scope": settings.CUMBUCA_OAUTH_SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{_authorization_url()}?{urlencode(params)}", state, verifier


def _basic_auth_header(client_id: str, client_secret: str) -> dict[str, str]:
    raw = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(raw.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _access_token_is_valid(
    access_token: str | None, token_expires_at: datetime | None
) -> bool:
    expires_at = _as_utc(token_expires_at)
    if not access_token or expires_at is None:
        return False
    return expires_at > datetime.now(timezone.utc) + timedelta(seconds=30)


def _store_token_response(
    session: Session,
    user: User,
    connection: OpenFinanceConnection,
    data: dict,
) -> None:
    """Store token response in both connection (source of truth) and user (backward compat)."""
    refresh_token = data.get("refresh_token")
    access_token = data.get("access_token")
    if not refresh_token and not access_token:
        raise HTTPException(
            status_code=400,
            detail="Open Finance did not return tokens.",
        )

    expires_in = data.get("expires_in")
    update_cumbuca_tokens(
        session,
        user,
        connection,
        refresh_token=refresh_token,
        access_token=access_token,
        expires_in=int(expires_in) if expires_in else None,
    )


def complete_authorization(
    session: Session,
    user: User,
    *,
    code: str,
    code_verifier: str,
) -> None:
    client_id, client_secret = ensure_oauth_client(session, user)
    response = httpx.post(
        _token_url(),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.CUMBUCA_REDIRECT_URI,
            "code_verifier": code_verifier,
            "client_id": client_id,
        },
        headers=_basic_auth_header(client_id, client_secret),
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail="Open Finance authorization failed.",
        )

    connection = get_cumbuca_connection(session, user.id)
    if not connection:
        connection = create_or_update_cumbuca_connection(
            session,
            user,
            oauth_client_id=client_id,
            oauth_client_secret=client_secret,
        )

    _store_token_response(session, user, connection, response.json())


def refresh_access_token(session: Session, user: User) -> str:
    """Refresh the Cumbuca access token, returning a valid token.

    Reads from connection table first, falls back to user columns for backward compat.
    """
    connection = get_cumbuca_connection(session, user.id)

    refresh_token = None
    access_token = None
    token_expires_at = None
    client_id = None
    client_secret = None

    if connection:
        refresh_token = connection.refresh_token
        access_token = connection.access_token
        token_expires_at = connection.token_expires_at
        client_id = connection.oauth_client_id
        client_secret = connection.oauth_client_secret

    if not refresh_token:
        refresh_token = user.cumbuca_refresh_token
        access_token = user.cumbuca_access_token
        token_expires_at = user.cumbuca_token_expires_at
        client_id = user.cumbuca_oauth_client_id
        client_secret = user.cumbuca_oauth_client_secret

    if not refresh_token:
        raise HTTPException(status_code=400, detail="Open Finance is not connected.")

    if _access_token_is_valid(access_token, token_expires_at):
        return access_token  # type: ignore[return-value]

    if not client_id or not client_secret:
        client_id, client_secret = ensure_oauth_client(session, user)
        connection = get_cumbuca_connection(session, user.id)

    response = httpx.post(
        _token_url(),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        headers=_basic_auth_header(client_id, client_secret),  # type: ignore[arg-type]
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=401,
            detail="Open Finance session expired. Reconnect your bank.",
        )
    data = response.json()

    if not connection:
        connection = create_or_update_cumbuca_connection(
            session,
            user,
            oauth_client_id=client_id or "",
            oauth_client_secret=client_secret or "",
            refresh_token=refresh_token,
        )

    _store_token_response(session, user, connection, data)

    new_access_token = data.get("access_token") or connection.access_token
    if not new_access_token:
        raise HTTPException(
            status_code=401,
            detail="Open Finance did not return an access token.",
        )
    return new_access_token


def disconnect_cumbuca(session: Session, user: User) -> None:
    """Disconnect Cumbuca by revoking tokens and clearing storage.

    Clears both connection table (source of truth) and user columns (backward compat).
    The connection row is marked as disconnected rather than deleted.
    """
    connection = get_cumbuca_connection(session, user.id)

    refresh_token = None
    client_id = None
    client_secret = None

    if connection:
        refresh_token = connection.refresh_token
        client_id = connection.oauth_client_id
        client_secret = connection.oauth_client_secret
    elif user.cumbuca_refresh_token:
        refresh_token = user.cumbuca_refresh_token
        client_id = user.cumbuca_oauth_client_id
        client_secret = user.cumbuca_oauth_client_secret

    if refresh_token and client_id and client_secret:
        try:
            httpx.post(
                _revocation_url(),
                data={
                    "token": refresh_token,
                    "token_type_hint": "refresh_token",
                    "client_id": client_id,
                },
                headers=_basic_auth_header(client_id, client_secret),
                timeout=15.0,
            )
        except httpx.HTTPError:
            pass

    if connection:
        connection.refresh_token = None
        connection.access_token = None
        connection.token_expires_at = None
        connection.status = "disconnected"
        connection.updated_at = datetime.now(timezone.utc)
        session.add(connection)

    user.cumbuca_refresh_token = None
    user.cumbuca_access_token = None
    user.cumbuca_token_expires_at = None
    user.cumbuca_connected_at = None
    session.add(user)
    session.commit()
