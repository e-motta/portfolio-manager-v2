import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, TypeVar

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Cumbuca MCP tool names (https://mcp.cumbuca.com/mcp)
TOOL_CANDIDATES = {
    "list_accounts": ("list_accounts",),
    "list_account_transactions": ("list_account_transactions",),
    "list_credit_cards": ("list_credit_cards",),
    "list_credit_card_bills": ("list_credit_card_bills",),
    "list_credit_card_bill_transactions": (
        "list_credit_card_bill_transactions",
    ),
    "list_investments": ("list_investments", "openfinance_list_investments"),
}


class CumbucaMcpError(Exception):
    pass


def format_mcp_error_message(raw: str) -> str:
    text = raw.strip()
    if not text:
        return "Open Finance MCP tool failed."
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(data, dict):
        return text
    message = data.get("message")
    if message:
        return str(message)
    error = data.get("error")
    if error:
        return str(error).replace("_", " ")
    return text


def _is_retryable_error(message: str) -> bool:
    lowered = message.lower()
    return "upstream_unavailable" in lowered or "temporarily unavailable" in lowered


def _run_async(coro: Awaitable[T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def _extract_json_payload(result: Any) -> Any:
    if result.isError:
        message = ""
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text:
                message = text
                break
        raise CumbucaMcpError(format_mcp_error_message(message or "Open Finance MCP tool failed."))

    for block in result.content or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
    return {}


def _unwrap_collection(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
    return []


async def _with_session(
    access_token: str,
    callback: Callable[[ClientSession, set[str]], Awaitable[T]],
) -> T:
    headers = {"Authorization": f"Bearer {access_token}"}
    timeout = httpx.Timeout(60.0, read=300.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
        async with streamable_http_client(
            settings.CUMBUCA_MCP_URL,
            http_client=http_client,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                return await callback(session, tool_names)


async def _call_named_tool(
    session: ClientSession,
    tool_names: set[str],
    purpose: str,
    arguments: dict[str, Any],
    *,
    required: bool = True,
    retries: int = 2,
) -> Any | None:
    last_error: CumbucaMcpError | None = None
    for candidate in TOOL_CANDIDATES[purpose]:
        if candidate not in tool_names:
            continue
        for attempt in range(retries + 1):
            result = await session.call_tool(candidate, arguments)
            try:
                return _extract_json_payload(result)
            except CumbucaMcpError as exc:
                last_error = exc
                if _is_retryable_error(str(exc)) and attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                break
        if last_error is not None:
            if required:
                raise last_error
            return None
    if not required:
        return None
    available = ", ".join(sorted(tool_names)) or "(none)"
    raise CumbucaMcpError(
        f"Open Finance tool for {purpose} is unavailable. Available tools: {available}"
    )


async def fetch_accounts_async(access_token: str) -> list[dict[str, Any]]:
    async def _run(session: ClientSession, tool_names: set[str]) -> list[dict[str, Any]]:
        payload = await _call_named_tool(session, tool_names, "list_accounts", {})
        return _unwrap_collection(payload, "accounts", "results", "items")

    return await _with_session(access_token, _run)


async def fetch_credit_cards_async(access_token: str) -> list[dict[str, Any]]:
    async def _run(session: ClientSession, tool_names: set[str]) -> list[dict[str, Any]]:
        payload = await _call_named_tool(session, tool_names, "list_credit_cards", {})
        return _unwrap_collection(payload, "credit_cards", "creditCards", "results")

    return await _with_session(access_token, _run)


async def fetch_account_transactions_async(
    access_token: str,
    *,
    account_id: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    async def _run(session: ClientSession, tool_names: set[str]) -> list[dict[str, Any]]:
        arguments = {
            "account_id": account_id,
            "from_date": start_date,
            "to_date": end_date,
        }
        payload = await _call_named_tool(
            session, tool_names, "list_account_transactions", arguments
        )
        return _unwrap_collection(payload, "transactions", "results", "items")

    return await _with_session(access_token, _run)


async def fetch_credit_card_bills_async(
    access_token: str,
    *,
    credit_card_account_id: str,
) -> list[dict[str, Any]]:
    async def _run(session: ClientSession, tool_names: set[str]) -> list[dict[str, Any]]:
        payload = await _call_named_tool(
            session,
            tool_names,
            "list_credit_card_bills",
            {"credit_card_account_id": credit_card_account_id},
        )
        return _unwrap_collection(payload, "bills", "creditCardBills", "results")

    return await _with_session(access_token, _run)


async def fetch_credit_card_bill_transactions_async(
    access_token: str,
    *,
    credit_card_account_id: str,
    bill_id: str,
) -> list[dict[str, Any]]:
    async def _run(session: ClientSession, tool_names: set[str]) -> list[dict[str, Any]]:
        payload = await _call_named_tool(
            session,
            tool_names,
            "list_credit_card_bill_transactions",
            {
                "credit_card_account_id": credit_card_account_id,
                "bill_id": bill_id,
            },
        )
        return _unwrap_collection(payload, "transactions", "results", "items")

    return await _with_session(access_token, _run)


async def fetch_all_transactions_async(
    access_token: str,
    *,
    start_date: str,
    end_date: str,
    year: int,
    month: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    async def _run(
        session: ClientSession,
        tool_names: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        transactions: list[dict[str, Any]] = []

        accounts_payload = await _call_named_tool(
            session, tool_names, "list_accounts", {}, required=False
        )
        accounts = _unwrap_collection(accounts_payload, "accounts", "results", "items")
        if not accounts:
            warnings.append("Could not load bank accounts from Open Finance.")

        cards_payload = await _call_named_tool(
            session, tool_names, "list_credit_cards", {}, required=False
        )
        credit_cards = _unwrap_collection(
            cards_payload, "credit_cards", "creditCards", "results"
        )

        for account in accounts:
            account_id = str(account.get("accountId") or account.get("account_id") or "")
            if not account_id:
                continue
            try:
                payload = await _call_named_tool(
                    session,
                    tool_names,
                    "list_account_transactions",
                    {
                        "account_id": account_id,
                        "from_date": start_date,
                        "to_date": end_date,
                    },
                )
            except CumbucaMcpError as exc:
                label = account.get("brandName") or account_id
                warnings.append(f"Bank account ({label}): {exc}")
                continue
            if payload is None:
                continue
            for tx in _unwrap_collection(payload, "transactions", "results", "items"):
                tx["_source_account"] = account
                tx["_source_kind"] = "bank"
                transactions.append(tx)

        relevant_bills = 0
        for card in credit_cards:
            card_id = str(
                card.get("creditCardAccountId")
                or card.get("credit_card_account_id")
                or ""
            )
            if not card_id:
                continue
            card_label = card.get("brandName") or card.get("name") or card_id
            try:
                bills_payload = await _call_named_tool(
                    session,
                    tool_names,
                    "list_credit_card_bills",
                    {"credit_card_account_id": card_id},
                )
            except CumbucaMcpError as exc:
                warnings.append(f"Credit card ({card_label}): {exc}")
                continue
            if bills_payload is None:
                continue
            bills = _unwrap_collection(
                bills_payload, "bills", "creditCardBills", "results"
            )
            for bill in bills:
                if not _bill_relevant_to_month(bill, year, month):
                    continue
                relevant_bills += 1
                bill_id = str(bill.get("billId") or bill.get("bill_id") or "")
                if not bill_id:
                    continue
                try:
                    bill_payload = await _call_named_tool(
                        session,
                        tool_names,
                        "list_credit_card_bill_transactions",
                        {
                            "credit_card_account_id": card_id,
                            "bill_id": bill_id,
                        },
                    )
                except CumbucaMcpError as exc:
                    closing = bill.get("billClosingDate") or "unknown bill"
                    warnings.append(f"Credit card bill ({card_label}, {closing}): {exc}")
                    continue
                if bill_payload is None:
                    continue
                statement_year, statement_month = _bill_statement_month(bill)
                for tx in _unwrap_collection(
                    bill_payload, "transactions", "results", "items"
                ):
                    tx["_source_account"] = card
                    tx["_source_kind"] = "credit_card"
                    tx["_statement_year"] = statement_year
                    tx["_statement_month"] = statement_month
                    transactions.append(tx)

        if credit_cards and relevant_bills == 0 and not warnings:
            warnings.append(
                "No credit card bills matched the selected month. Check that the statement has closed for that period."
            )

        return accounts, credit_cards, transactions, warnings

    return await _with_session(access_token, _run)


def _bill_relevant_to_month(bill: dict[str, Any], year: int, month: int) -> bool:
    statement_year, statement_month = _bill_statement_month(bill)
    return statement_year == year and statement_month == month


def _bill_statement_month(bill: dict[str, Any]) -> tuple[int, int]:
    for key in ("billClosingDate", "dueDate"):
        value = bill.get(key)
        if not value:
            continue
        try:
            parsed = date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
        return parsed.year, parsed.month
    return 0, 0


async def fetch_investments_async(access_token: str) -> list[dict[str, Any]]:
    async def _run(session: ClientSession, tool_names: set[str]) -> list[dict[str, Any]]:
        payload = await _call_named_tool(
            session, tool_names, "list_investments", {}, required=False
        )
        if payload is None:
            return []
        return _unwrap_collection(payload, "investments", "results", "items")

    return await _with_session(access_token, _run)


async def list_tool_names_async(access_token: str) -> list[str]:
    async def _run(_session: ClientSession, tool_names: set[str]) -> list[str]:
        return sorted(tool_names)

    return await _with_session(access_token, _run)


def fetch_all_transactions(
    access_token: str,
    *,
    start_date: str,
    end_date: str,
    year: int,
    month: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    return _run_async(
        fetch_all_transactions_async(
            access_token,
            start_date=start_date,
            end_date=end_date,
            year=year,
            month=month,
        )
    )


def fetch_investments(access_token: str) -> list[dict[str, Any]]:
    return _run_async(fetch_investments_async(access_token))


def list_tool_names(access_token: str) -> list[str]:
    return _run_async(list_tool_names_async(access_token))
