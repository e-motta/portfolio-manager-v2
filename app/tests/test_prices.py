import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services import prices

_ORIGINAL_RESOLVE = prices.resolve_purchase_usd_brl_rate


@pytest.fixture(autouse=True)
def restore_price_resolvers(mock_prices, monkeypatch):
    monkeypatch.setattr(prices, "resolve_purchase_usd_brl_rate", _ORIGINAL_RESOLVE)


def test_fetch_ptax_usd_brl_rate_parses_response():
    payload = json.dumps({"value": [{"cotacaoVenda": 6.0509}]}).encode()
    mock_response = MagicMock()
    mock_response.read.return_value = payload
    mock_response.__enter__.return_value = mock_response

    with patch("app.services.prices.urllib.request.urlopen", return_value=mock_response):
        rate = prices.fetch_ptax_usd_brl_rate(date(2024, 12, 16))

    assert rate == Decimal("6.0509")


def test_fetch_ptax_usd_brl_rate_returns_none_on_empty_value():
    payload = json.dumps({"value": []}).encode()
    mock_response = MagicMock()
    mock_response.read.return_value = payload
    mock_response.__enter__.return_value = mock_response

    with patch("app.services.prices.urllib.request.urlopen", return_value=mock_response):
        rate = prices.fetch_ptax_usd_brl_rate(date(2024, 12, 16))

    assert rate is None


def test_fetch_ptax_usd_brl_rate_returns_none_on_network_error():
    with patch(
        "app.services.prices.urllib.request.urlopen",
        side_effect=OSError("network down"),
    ):
        rate = prices.fetch_ptax_usd_brl_rate(date(2024, 12, 16))

    assert rate is None


def test_resolve_purchase_usd_brl_rate_uses_ptax_when_available():
    with patch.object(prices, "fetch_ptax_usd_brl_rate", return_value=Decimal("6.05")):
        rate, provisional = prices.resolve_purchase_usd_brl_rate(date(2024, 12, 16))

    assert rate == Decimal("6.05")
    assert provisional is False


def test_resolve_purchase_usd_brl_rate_falls_back_to_estimated():
    with (
        patch.object(prices, "fetch_ptax_usd_brl_rate", return_value=None),
        patch.object(prices, "fetch_usd_brl_rate", return_value=Decimal("5.5")),
    ):
        rate, provisional = prices.resolve_purchase_usd_brl_rate(date(2024, 12, 16))

    assert rate == Decimal("5.5")
    assert provisional is True


def test_ptax_url_uses_mm_dd_yyyy_format():
    url = prices._ptax_url(date(2024, 12, 16))
    assert "@dataInicialCotacao='12-16-2024'" in url
    assert "@dataFinalCotacao='12-16-2024'" in url


def test_refresh_provisional_ptax_rates_updates_lots(session, exchange_type):
    from app.tests.conftest import make_lot

    lot = make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("10"),
        Decimal("100"),
        purchase_date=date(2024, 12, 16),
        usd_brl_rate=Decimal("5.5"),
        provisional_fx=True,
    )

    with patch.object(prices, "fetch_ptax_usd_brl_rate", return_value=Decimal("6.05")):
        updated = prices.refresh_provisional_ptax_rates(session)

    assert updated == 1
    session.refresh(lot)
    assert lot.usd_brl_rate == Decimal("6.05")
    assert lot.purchase_price_brl == Decimal("605")
    assert lot.provisional_fx is False


def test_refresh_provisional_ptax_rates_skips_when_ptax_unavailable(session, exchange_type):
    from app.tests.conftest import make_lot

    lot = make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("10"),
        Decimal("100"),
        purchase_date=date(2024, 12, 16),
        usd_brl_rate=Decimal("5.5"),
        provisional_fx=True,
    )

    with patch.object(prices, "fetch_ptax_usd_brl_rate", return_value=None):
        updated = prices.refresh_provisional_ptax_rates(session)

    assert updated == 0
    session.refresh(lot)
    assert lot.usd_brl_rate == Decimal("5.5")
    assert lot.provisional_fx is True


def test_refresh_provisional_ptax_rates_caches_ptax_by_date(session, exchange_type):
    from app.tests.conftest import make_lot

    make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("10"),
        Decimal("100"),
        purchase_date=date(2024, 12, 16),
        provisional_fx=True,
    )
    make_lot(
        session,
        exchange_type.id,
        "VOO",
        Decimal("5"),
        Decimal("200"),
        purchase_date=date(2024, 12, 16),
        provisional_fx=True,
    )

    with patch.object(
        prices,
        "fetch_ptax_usd_brl_rate",
        return_value=Decimal("6.05"),
    ) as fetch_ptax:
        updated = prices.refresh_provisional_ptax_rates(session)

    assert updated == 2
    fetch_ptax.assert_called_once_with(date(2024, 12, 16))
