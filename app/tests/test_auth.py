from unittest.mock import AsyncMock, patch

from authlib.integrations.base_client.errors import MismatchingStateError
from sqlmodel import select

from app.models.asset_type import AssetType
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.auth import ensure_user_portfolio, find_or_create_user


def test_google_callback_redirects_to_login_on_state_mismatch(client):
    with patch("app.web.routes.auth.oauth") as mock_oauth:
        mock_oauth.google.authorize_access_token = AsyncMock(
            side_effect=MismatchingStateError()
        )
        response = client.get("/auth/callback?code=fake", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/auth/login?error=")

    login_page = client.get(response.headers["location"])
    assert login_page.status_code == 200
    assert "Login session expired" in login_page.text


def test_find_or_create_user_is_idempotent(session):
    user = find_or_create_user(
        session,
        email="test@example.com",
        google_sub="google-sub-123",
        name="Test",
        picture_url="https://example.com/photo.jpg",
    )
    again = find_or_create_user(
        session,
        email="test@example.com",
        google_sub="google-sub-123",
        name="Test M",
        picture_url="https://example.com/photo2.jpg",
    )
    assert user.id == again.id
    assert again.name == "Test M"


def test_ensure_user_portfolio_creates_defaults_for_new_user(session):
    existing_user = session.exec(select(User)).one()
    existing_portfolio = session.exec(select(Portfolio)).one()
    assert existing_portfolio.user_id == existing_user.id

    user = User(
        email="other@example.com",
        google_sub="other-sub",
        name="Other",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    portfolio = ensure_user_portfolio(session, user)
    assert portfolio.user_id == user.id
    assert portfolio.id != existing_portfolio.id

    asset_types = session.exec(
        select(AssetType).where(AssetType.portfolio_id == portfolio.id)
    ).all()
    assert len(asset_types) == 5


def test_ensure_user_portfolio_is_idempotent(session):
    user = session.exec(select(User)).one()
    first = ensure_user_portfolio(session, user)
    again = ensure_user_portfolio(session, user)
    assert first.id == again.id
