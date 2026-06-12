from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine, select

from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.models.asset_type import AssetType, DEFAULT_ASSET_TYPES
from app.models.portfolio import Portfolio

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def run_migrations() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


def init_db(session: Session) -> None:
    portfolio = session.exec(select(Portfolio)).first()
    if not portfolio:
        portfolio = Portfolio(name="My Portfolio")
        session.add(portfolio)
        session.commit()
        session.refresh(portfolio)

    existing_types = session.exec(select(AssetType)).all()
    if not existing_types:
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
