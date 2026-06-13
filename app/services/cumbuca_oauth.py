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
from app.models.user import User

OAUTH_PURPOSE_CUMBUCA = "cumbuca"
OPEN_FINANCE_SOURCE = "open_finance"


def user_has_cumbuca(user: User) -> bool:
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


def ensure_oauth_client(session: Session, user: User) -> None:
    if user.cumbuca_oauth_client_id and user.cumbuca_oauth_client_secret:
        return

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
    user.cumbuca_oauth_client_id = client_id
    user.cumbuca_oauth_client_secret = client_secret
    session.add(user)
    session.commit()
    session.refresh(user)


def build_authorization_request(session: Session, user: User) -> tuple[str, str, str]:
    ensure_oauth_client(session, user)
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    params = {
        "response_type": "code",
        "client_id": user.cumbuca_oauth_client_id,
        "redirect_uri": settings.CUMBUCA_REDIRECT_URI,
        "scope": settings.CUMBUCA_OAUTH_SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{_authorization_url()}?{urlencode(params)}", state, verifier


def _basic_auth_header(user: User) -> dict[str, str]:
    raw = f"{user.cumbuca_oauth_client_id}:{user.cumbuca_oauth_client_secret}"
    encoded = base64.b64encode(raw.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _access_token_is_valid(user: User) -> bool:
    expires_at = _as_utc(user.cumbuca_token_expires_at)
    if not user.cumbuca_access_token or expires_at is None:
        return False
    return expires_at > datetime.now(timezone.utc) + timedelta(seconds=30)


def _store_token_response(session: Session, user: User, data: dict) -> None:
    refresh_token = data.get("refresh_token")
    access_token = data.get("access_token")
    if not refresh_token and not access_token:
        raise HTTPException(
            status_code=400,
            detail="Open Finance did not return tokens.",
        )
    if refresh_token:
        user.cumbuca_refresh_token = refresh_token
    if access_token:
        user.cumbuca_access_token = access_token
    expires_in = data.get("expires_in")
    if expires_in:
        user.cumbuca_token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(expires_in)
        )
    user.cumbuca_connected_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)


def complete_authorization(
    session: Session,
    user: User,
    *,
    code: str,
    code_verifier: str,
) -> None:
    ensure_oauth_client(session, user)
    response = httpx.post(
        _token_url(),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.CUMBUCA_REDIRECT_URI,
            "code_verifier": code_verifier,
            "client_id": user.cumbuca_oauth_client_id,
        },
        headers=_basic_auth_header(user),
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail="Open Finance authorization failed.",
        )
    _store_token_response(session, user, response.json())


def refresh_access_token(session: Session, user: User) -> str:
    if not user.cumbuca_refresh_token:
        raise HTTPException(status_code=400, detail="Open Finance is not connected.")

    if _access_token_is_valid(user):
        return user.cumbuca_access_token  # type: ignore[return-value]

    ensure_oauth_client(session, user)
    response = httpx.post(
        _token_url(),
        data={
            "grant_type": "refresh_token",
            "refresh_token": user.cumbuca_refresh_token,
            "client_id": user.cumbuca_oauth_client_id,
        },
        headers=_basic_auth_header(user),
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=401,
            detail="Open Finance session expired. Reconnect your bank.",
        )
    data = response.json()
    _store_token_response(session, user, data)
    if not user.cumbuca_access_token:
        raise HTTPException(
            status_code=401,
            detail="Open Finance did not return an access token.",
        )
    return user.cumbuca_access_token


def disconnect_cumbuca(session: Session, user: User) -> None:
    if user.cumbuca_refresh_token and user.cumbuca_oauth_client_id:
        try:
            httpx.post(
                _revocation_url(),
                data={
                    "token": user.cumbuca_refresh_token,
                    "token_type_hint": "refresh_token",
                    "client_id": user.cumbuca_oauth_client_id,
                },
                headers=_basic_auth_header(user),
                timeout=15.0,
            )
        except httpx.HTTPError:
            pass

    user.cumbuca_refresh_token = None
    user.cumbuca_access_token = None
    user.cumbuca_token_expires_at = None
    user.cumbuca_connected_at = None
    session.add(user)
    session.commit()
