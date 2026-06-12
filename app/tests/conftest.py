import os

os.environ["TESTING"] = "1"

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.core.auth import bind_user_to_session
from app.core.config import settings
from app.core.db import init_db
from app.services.auth import ensure_user_portfolio
from app.main import app
from app.models.asset_type import AssetType
from app.models.dividend import Dividend
from app.models.investment import Investment
from app.models.security import SecurityLot
from app.models.symbol_target import SymbolTarget
from app.models.user import User
from app.services.dividends import compute_net_amount
from app.services import prices


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        settings.TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_db(session)
        user = User(
            email="test@example.com",
            google_sub="test-google-sub",
            name="Test User",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        ensure_user_portfolio(session, user)
        bind_user_to_session(session, user)
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        yield session

    from app.core import db

    app.dependency_overrides[db.get_session] = get_session_override

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(name="exchange_type")
def exchange_type_fixture(session: Session) -> AssetType:
    return session.exec(
        select(AssetType).where(AssetType.is_exchange_traded.is_(True))  # type: ignore[attr-defined]
    ).one()


@pytest.fixture(autouse=True)
def mock_prices(monkeypatch):
    def _fetch(symbols):
        symbol_list = list(symbols)
        return {
            symbol: prices.TickerInfo(
                symbol=symbol,
                name=symbol,
                latest_price=Decimal("100"),
            )
            for symbol in symbol_list
        }

    def _estimated_purchase_rate(_date):
        return Decimal("5"), True

    monkeypatch.setattr(prices, "fetch_tickers_info", _fetch)
    monkeypatch.setattr(prices, "fetch_usd_brl_rate", lambda: Decimal("5"))
    monkeypatch.setattr(prices, "resolve_purchase_usd_brl_rate", _estimated_purchase_rate)
    monkeypatch.setattr(
        "app.web.routes.securities.fetch_tickers_info",
        _fetch,
    )
    monkeypatch.setattr(
        "app.web.routes.securities.resolve_purchase_usd_brl_rate",
        _estimated_purchase_rate,
    )
    monkeypatch.setattr(
        "app.services.ib_statement.fetch_tickers_info",
        _fetch,
    )
    monkeypatch.setattr(
        "app.services.ib_statement.resolve_purchase_usd_brl_rate",
        _estimated_purchase_rate,
    )


def make_asset_type(
    session: Session,
    portfolio_id,
    name: str,
    target_pct: Decimal | None,
    current_value: Decimal,
    is_exchange_traded: bool = False,
) -> AssetType:
    asset_type = AssetType(
        portfolio_id=portfolio_id,
        name=name,
        slug=name.lower().replace(" ", "-"),
        target_pct=target_pct,
        current_value=current_value,
        is_exchange_traded=is_exchange_traded,
    )
    session.add(asset_type)
    session.commit()
    session.refresh(asset_type)
    return asset_type


def make_symbol_target(
    session: Session,
    asset_type_id,
    symbol: str,
    target_pct: Decimal,
) -> SymbolTarget:
    target = SymbolTarget(
        asset_type_id=asset_type_id,
        symbol=symbol,
        name=symbol,
        target_pct=target_pct,
    )
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


def make_lot(
    session: Session,
    asset_type_id,
    symbol: str,
    position: Decimal,
    purchase_price_usd: Decimal,
    *,
    target_pct: Decimal | None = None,
    purchase_date: date | None = None,
    usd_brl_rate: Decimal = Decimal("5"),
    provisional_fx: bool = False,
) -> SecurityLot:
    if target_pct is not None:
        existing = session.exec(
            select(SymbolTarget).where(
                SymbolTarget.asset_type_id == asset_type_id,
                SymbolTarget.symbol == symbol,
            )
        ).first()
        if not existing:
            make_symbol_target(session, asset_type_id, symbol, target_pct)

    purchase_brl = purchase_price_usd * usd_brl_rate
    lot = SecurityLot(
        asset_type_id=asset_type_id,
        symbol=symbol,
        name=symbol,
        position=position,
        purchase_date=purchase_date or date.today(),
        purchase_price_usd=purchase_price_usd,
        purchase_price_brl=purchase_brl,
        usd_brl_rate=usd_brl_rate,
        provisional_fx=provisional_fx,
        current_price_usd=purchase_price_usd,
        current_price_brl=purchase_brl,
    )
    session.add(lot)
    session.commit()
    session.refresh(lot)
    return lot


def make_security(*args, **kwargs):
    return make_lot(*args, **kwargs)


def make_dividend(
    session: Session,
    asset_type_id,
    symbol: str,
    pay_date: date,
    gross_amount_usd: Decimal,
    *,
    withholding_tax_usd: Decimal = Decimal("0"),
    source: str = "manual",
    import_key: str | None = None,
) -> Dividend:
    dividend = Dividend(
        asset_type_id=asset_type_id,
        symbol=symbol,
        pay_date=pay_date,
        gross_amount_usd=gross_amount_usd,
        withholding_tax_usd=withholding_tax_usd,
        net_amount_usd=compute_net_amount(gross_amount_usd, withholding_tax_usd),
        source=source,
        import_key=import_key,
    )
    session.add(dividend)
    session.commit()
    session.refresh(dividend)
    return dividend


def make_investment(
    session: Session,
    asset_type_id,
    name: str,
    current_value: Decimal,
    institution: str = "Test Bank",
) -> Investment:
    investment = Investment(
        asset_type_id=asset_type_id,
        institution=institution,
        name=name,
        current_value=current_value,
    )
    session.add(investment)
    session.commit()
    session.refresh(investment)
    return investment
