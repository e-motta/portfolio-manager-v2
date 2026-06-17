from sqlmodel import Session, select

from app.models.asset_type import DEFAULT_ASSET_TYPES, AssetType
from app.models.portfolio import Portfolio
from app.models.user import User


def find_or_create_user(
    session: Session,
    *,
    email: str,
    google_sub: str,
    name: str,
    picture_url: str,
) -> User:
    user = session.exec(select(User).where(User.google_sub == google_sub)).first()
    if user:
        user.name = name or user.name
        user.picture_url = picture_url or user.picture_url
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    user = session.exec(select(User).where(User.email == email)).first()
    if user:
        user.google_sub = google_sub
        user.name = name or user.name
        user.picture_url = picture_url or user.picture_url
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    user = User(
        email=email,
        google_sub=google_sub,
        name=name,
        picture_url=picture_url,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def ensure_user_portfolio(session: Session, user: User) -> Portfolio:
    portfolio = session.exec(
        select(Portfolio).where(Portfolio.user_id == user.id)
    ).first()
    if portfolio:
        return portfolio

    portfolio = Portfolio(name="My Portfolio", user_id=user.id)
    session.add(portfolio)
    session.commit()
    session.refresh(portfolio)

    for item in DEFAULT_ASSET_TYPES:
        session.add(
            AssetType(
                portfolio_id=portfolio.id,
                name=item["name"],
                slug=item["slug"],
                is_exchange_traded=item["is_exchange_traded"],
                target_pct=item["target_pct"],
                current_value=item["current_value"],
            )
        )
    session.commit()
    return portfolio
