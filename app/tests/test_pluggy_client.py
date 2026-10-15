"""Tests for the Pluggy API client."""

from unittest.mock import patch

import httpx
import pytest

from app.services.pluggy_client import (
    PAGE_SIZE,
    PaginationCapWarning,
    PluggyAuthError,
    PluggyInvalidItemIdError,
    _get,
    _paginate,
    _validate_uuid,
    clear_auth_cache,
    fetch_item,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_auth_cache()
    PaginationCapWarning.pop_all()
    yield
    clear_auth_cache()
    PaginationCapWarning.pop_all()


def test_validate_uuid_accepts_canonical_form():
    assert _validate_uuid("550e8400-e29b-41d4-a716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"


def test_validate_uuid_rejects_path_injection():
    with pytest.raises(PluggyInvalidItemIdError):
        _validate_uuid("../accounts")
    with pytest.raises(PluggyInvalidItemIdError):
        _validate_uuid("not-a-uuid")
    with pytest.raises(PluggyInvalidItemIdError):
        _validate_uuid("550e8400-e29b-41d4-a716-446655440000/../secrets")


def test_fetch_item_rejects_invalid_id_before_request():
    with patch("app.services.pluggy_client._get") as mock_get:
        with pytest.raises(PluggyInvalidItemIdError):
            fetch_item("../items")
        mock_get.assert_not_called()


def test_paginate_uses_page_size_500():
    with patch("app.services.pluggy_client._get") as mock_get:
        mock_get.return_value = {"results": [{"id": "1"}], "totalPages": 1, "total": 1}
        results = _paginate("/transactions", {"accountId": "abc"})
    assert results == [{"id": "1"}]
    params = mock_get.call_args.args[1]
    assert params["pageSize"] == PAGE_SIZE
    assert params["page"] == 1


def test_paginate_warns_when_page_cap_is_hit():
    from app.services.pluggy_client import MAX_PAGES

    def _page(_path, params):
        return {
            "results": [{"id": params["page"]}],
            "totalPages": MAX_PAGES + 5,
            "total": (MAX_PAGES + 5) * PAGE_SIZE,
        }

    with patch("app.services.pluggy_client._get", side_effect=_page):
        results = _paginate("/transactions")

    assert len(results) == MAX_PAGES
    warnings = PaginationCapWarning.pop_all()
    assert warnings
    assert "pagination cap" in warnings[0]


def _response(status_code: int, payload: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://api.pluggy.ai/items")
    return httpx.Response(status_code, json=payload or {}, request=request)


def test_get_retries_once_after_401():
    with patch("app.services.pluggy_client._authenticate", return_value="key"), \
         patch("app.services.pluggy_client.httpx.get") as mock_get:
        mock_get.side_effect = [_response(401), _response(200, {"id": "ok"})]
        data = _get("/items/x")

    assert data == {"id": "ok"}
    assert mock_get.call_count == 2


def test_get_raises_after_second_401():
    with patch("app.services.pluggy_client._authenticate", return_value="key"), \
         patch("app.services.pluggy_client.httpx.get") as mock_get:
        mock_get.side_effect = [_response(401), _response(401)]
        with pytest.raises(PluggyAuthError):
            _get("/items/x")
    assert mock_get.call_count == 2
