"""Pluggy API client for Meu Pluggy integration.

Authenticates using client credentials and provides methods to fetch
items (bank connections), accounts, transactions, credit cards, and investments.

API docs: https://docs.pluggy.ai
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PluggyInvalidItemIdError(Exception):
    """Invalid Pluggy item ID (not a valid UUID)."""


class PluggyError(Exception):
    """Error from Pluggy API."""


class PluggyAuthError(PluggyError):
    """Authentication failed with Pluggy."""


@dataclass
class PluggyApiKey:
    """Cached API key with expiration tracking."""

    api_key: str
    expires_at: datetime

    def is_valid(self) -> bool:
        return datetime.now(timezone.utc) < self.expires_at - timedelta(minutes=5)


_api_key_cache: PluggyApiKey | None = None


def _get_base_url() -> str:
    return settings.PLUGGY_API_URL.rstrip("/")


def _is_configured() -> bool:
    return bool(settings.PLUGGY_CLIENT_ID and settings.PLUGGY_CLIENT_SECRET)


def is_pluggy_available() -> bool:
    """Check if Pluggy credentials are configured."""
    return _is_configured()


def _authenticate() -> str:
    """Authenticate with Pluggy and return an API key.

    POST /auth with clientId and clientSecret returns an apiKey
    that expires in a certain time (default 2h).
    """
    global _api_key_cache

    if _api_key_cache and _api_key_cache.is_valid():
        return _api_key_cache.api_key

    if not _is_configured():
        raise PluggyAuthError("Pluggy credentials not configured.")

    url = f"{_get_base_url()}/auth"
    payload = {
        "clientId": settings.PLUGGY_CLIENT_ID,
        "clientSecret": settings.PLUGGY_CLIENT_SECRET,
    }

    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("Pluggy auth failed: %s", exc.response.status_code)
        raise PluggyAuthError("Failed to authenticate with Pluggy.") from exc
    except httpx.HTTPError as exc:
        logger.warning("Pluggy auth error: %s", exc)
        raise PluggyAuthError("Could not connect to Pluggy.") from exc

    data = response.json()
    api_key = data.get("apiKey")
    if not api_key:
        raise PluggyAuthError("Pluggy did not return an API key.")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)

    _api_key_cache = PluggyApiKey(api_key=api_key, expires_at=expires_at)
    return api_key


def _make_headers() -> dict[str, str]:
    api_key = _authenticate()
    return {
        "X-API-KEY": api_key,
        "Accept": "application/json",
    }


def _get(path: str, params: dict[str, Any] | None = None, *, _retry_on_401: bool = True) -> Any:
    """Make authenticated GET request to Pluggy API.

    On a 401 response, clears the cached API key and retries once.
    """
    url = f"{_get_base_url()}{path}"
    headers = _make_headers()

    try:
        response = httpx.get(url, headers=headers, params=params, timeout=60.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Pluggy API error: %s %s", exc.response.status_code, path)
        if exc.response.status_code == 401:
            global _api_key_cache
            _api_key_cache = None
            if _retry_on_401:
                logger.info("Retrying Pluggy request after 401: %s", path)
                return _get(path, params, _retry_on_401=False)
            raise PluggyAuthError("Pluggy authentication expired.") from exc
        raise PluggyError(f"Pluggy API error: {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        logger.warning("Pluggy request failed: %s", exc)
        raise PluggyError("Could not connect to Pluggy.") from exc


PAGE_SIZE = 500
MAX_PAGES = 100


class PaginationCapWarning:
    """Container for pagination cap warnings."""

    _warnings: list[str] = []

    @classmethod
    def add(cls, message: str) -> None:
        cls._warnings.append(message)

    @classmethod
    def pop_all(cls) -> list[str]:
        warnings = cls._warnings[:]
        cls._warnings = []
        return warnings


def _paginate(path: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Fetch all pages of a paginated Pluggy endpoint.

    Uses pageSize=500 per request. Warns if the page cap is hit.
    """
    results: list[dict] = []
    page = 1
    params = dict(params or {})
    params["pageSize"] = PAGE_SIZE

    while page <= MAX_PAGES:
        params["page"] = page
        data = _get(path, params)

        if isinstance(data, dict):
            items = data.get("results", [])
            if isinstance(items, list):
                results.extend(items)
            total_pages = data.get("totalPages", 1)
            total_items = data.get("total", len(results))
            if page >= total_pages:
                break
            if page >= MAX_PAGES and total_pages > MAX_PAGES:
                PaginationCapWarning.add(
                    f"Pluggy pagination cap reached for {path}: "
                    f"fetched {len(results)} of {total_items} items"
                )
                break
        else:
            break

        page += 1

    return results


def _cursor_next_path(path: str, next_value: str) -> str:
    """Turn a v2 ``next`` value into a request path.

    Pluggy returns a ready-to-use query string (``?accountId=...&after=...``)
    that must be appended as-is. Some payloads use a full URL or a bare
    query string; accept those without rebuilding ``after``.
    """
    text = str(next_value).strip()
    if not text:
        return path
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
    if text.startswith("/"):
        return text
    if text.startswith("?"):
        return f"{path}{text}"
    return f"{path}?{text}"


def _paginate_cursor(path: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Fetch every page of a Pluggy v2 cursor endpoint.

    The first request uses ``params``. Later pages follow ``next`` until it is
    null. Warns if the page cap is hit. Must not send ``page`` / ``pageSize``.
    """
    results: list[dict] = []
    request_path = path
    request_params: dict[str, Any] | None = dict(params or {})
    page = 1

    while page <= MAX_PAGES:
        data = _get(request_path, request_params)
        if not isinstance(data, dict):
            break

        items = data.get("results", [])
        if isinstance(items, list):
            results.extend(items)

        next_value = data.get("next")
        if not next_value:
            break
        if page >= MAX_PAGES:
            PaginationCapWarning.add(
                f"Pluggy pagination cap reached for {path}: "
                f"fetched {len(results)} items"
            )
            break

        request_path = _cursor_next_path(path, str(next_value))
        request_params = None
        page += 1

    return results


def _validate_uuid(value: str) -> str:
    """Validate that a string is a valid UUID, returning it in lowercase canonical form.

    Raises PluggyInvalidItemIdError if the value is not a valid UUID.
    This is critical for security to prevent path injection attacks.
    """
    try:
        parsed = UUID(value)
        return str(parsed)
    except (ValueError, TypeError) as exc:
        raise PluggyInvalidItemIdError(f"Invalid item ID: {value!r} is not a valid UUID.") from exc


def fetch_item(item_id: str) -> dict[str, Any]:
    """Fetch a single item by ID.

    Note: Meu Pluggy (personal/free) accounts cannot list items via API.
    Users must manually provide item IDs from the Meu Pluggy dashboard.
    This endpoint validates that the item exists and returns its details.

    Raises PluggyInvalidItemIdError if item_id is not a valid UUID.
    """
    validated_id = _validate_uuid(item_id)
    return _get(f"/items/{validated_id}")


def validate_item(item_id: str) -> tuple[bool, dict[str, Any] | str]:
    """Validate an item ID and return its details or error message.

    Returns (True, item_data) if valid, (False, error_message) if not.
    """
    try:
        data = fetch_item(item_id)
        if not data or not data.get("id"):
            return False, "Item not found."
        return True, data
    except PluggyInvalidItemIdError as exc:
        return False, str(exc)
    except PluggyAuthError as exc:
        return False, str(exc)
    except PluggyError as exc:
        return False, str(exc)


def fetch_accounts(item_id: str) -> list[dict[str, Any]]:
    """Fetch accounts for an item."""
    validated_id = _validate_uuid(item_id)
    return _paginate("/accounts", {"itemId": validated_id})


def fetch_transactions(
    account_id: str,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch transactions for an account via GET /v2/transactions.

    v1 ``GET /transactions`` is deprecated (410 ENDPOINT_DEPRECATED). v2
    accepts ``accountId``, ``dateFrom``, and ``dateTo`` and paginates with
    a ``next`` cursor. It rejects ``from`` / ``to`` / ``pageSize``.
    """
    validated_id = _validate_uuid(account_id)
    params: dict[str, Any] = {"accountId": validated_id}
    if from_date:
        params["dateFrom"] = from_date.isoformat()
    if to_date:
        params["dateTo"] = to_date.isoformat()

    return _paginate_cursor("/v2/transactions", params)


def fetch_credit_cards(item_id: str) -> list[dict[str, Any]]:
    """Fetch credit card accounts for an item.

    Note: item_id is validated as a UUID by fetch_accounts.
    """
    accounts = fetch_accounts(item_id)
    return [acc for acc in accounts if acc.get("type") == "CREDIT"]


def fetch_credit_card_bills(account_id: str) -> list[dict[str, Any]]:
    """Fetch credit card bills for an account."""
    validated_id = _validate_uuid(account_id)
    return _paginate("/bills", {"accountId": validated_id})


def fetch_bill_transactions(bill_id: str) -> list[dict[str, Any]]:
    """Fetch transactions for a specific credit card bill.

    Note: Pluggy returns transactions via the regular /transactions endpoint
    filtered by date range from the bill. This method fetches the bill
    and then its transactions.
    """
    validated_bill_id = _validate_uuid(bill_id)
    bill = _get(f"/bills/{validated_bill_id}")
    if not bill:
        return []

    account_id = bill.get("accountId")
    close_date = bill.get("closeDate")
    due_date = bill.get("dueDate")

    if not account_id or not close_date:
        return []

    close = date.fromisoformat(str(close_date)[:10])
    due = date.fromisoformat(str(due_date)[:10]) if due_date else close

    prev_close = close - timedelta(days=30)
    return fetch_transactions(account_id, from_date=prev_close, to_date=due)


def fetch_investments(item_id: str) -> list[dict[str, Any]]:
    """Fetch investment positions for an item."""
    validated_id = _validate_uuid(item_id)
    return _paginate("/investments", {"itemId": validated_id})


def fetch_investment_transactions(
    investment_id: str,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch transactions for a specific investment."""
    validated_id = _validate_uuid(investment_id)
    params: dict[str, Any] = {"investmentId": validated_id}
    if from_date:
        params["from"] = from_date.isoformat()
    if to_date:
        params["to"] = to_date.isoformat()

    return _paginate("/investment-transactions", params)


def fetch_identity(item_id: str) -> dict[str, Any] | None:
    """Fetch identity info for an item (CPF holder info)."""
    try:
        validated_id = _validate_uuid(item_id)
        data = _get("/identity", {"itemId": validated_id})
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
            return results[0] if results else None
        return data if isinstance(data, dict) else None
    except (PluggyError, PluggyInvalidItemIdError):
        return None


@dataclass
class PluggyItem:
    """Represents a Pluggy item (bank connection)."""

    id: str
    connector_id: int
    connector_name: str
    status: str
    institution_name: str
    last_updated_at: datetime | None
    created_at: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "PluggyItem":
        connector = data.get("connector", {})
        return cls(
            id=str(data.get("id", "")),
            connector_id=connector.get("id", 0),
            connector_name=connector.get("name", ""),
            status=data.get("status", "UNKNOWN"),
            institution_name=connector.get("institutionName", connector.get("name", "Unknown")),
            last_updated_at=_parse_datetime(data.get("lastUpdatedAt")),
            created_at=_parse_datetime(data.get("createdAt")),
        )


@dataclass
class PluggyAccount:
    """Represents a Pluggy account."""

    id: str
    item_id: str
    type: str
    subtype: str
    name: str
    balance: Decimal
    currency: str
    number: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "PluggyAccount":
        return cls(
            id=str(data.get("id", "")),
            item_id=str(data.get("itemId", "")),
            type=data.get("type", ""),
            subtype=data.get("subtype", ""),
            name=data.get("name", ""),
            balance=_parse_decimal(data.get("balance", 0)),
            currency=data.get("currencyCode", "BRL"),
            number=data.get("number"),
        )


@dataclass
class PluggyTransaction:
    """Represents a Pluggy transaction."""

    id: str
    account_id: str
    description: str
    amount: Decimal
    currency: str
    date: date
    type: str
    category: str | None
    payment_data: dict[str, Any] | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "PluggyTransaction":
        return cls(
            id=str(data.get("id", "")),
            account_id=str(data.get("accountId", "")),
            description=data.get("description", ""),
            amount=_parse_decimal(data.get("amount", 0)),
            currency=data.get("currencyCode", "BRL"),
            date=_parse_date(data.get("date")) or date.today(),
            type=data.get("type", ""),
            category=data.get("category"),
            payment_data=data.get("paymentData"),
        )


@dataclass
class PluggyInvestment:
    """Represents a Pluggy investment position."""

    id: str
    item_id: str
    type: str
    subtype: str | None
    name: str
    value: Decimal
    quantity: Decimal | None
    currency: str
    code: str | None
    isin: str | None
    institution_name: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "PluggyInvestment":
        return cls(
            id=str(data.get("id", "")),
            item_id=str(data.get("itemId", "")),
            type=data.get("type", ""),
            subtype=data.get("subtype"),
            name=data.get("name", ""),
            value=_parse_decimal(data.get("value") or data.get("balance", 0)),
            quantity=_parse_decimal(data.get("quantity")),
            currency=data.get("currencyCode", "BRL"),
            code=data.get("code"),
            isin=data.get("isin"),
            institution_name=data.get("institutionValue"),
        )


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def clear_auth_cache() -> None:
    """Clear the cached API key (for testing)."""
    global _api_key_cache
    _api_key_cache = None
