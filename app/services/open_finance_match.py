"""Cross-provider matching helpers for Open Finance imports.

Used at preview time to flag rows that look like the same transaction
already imported from the other provider.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, select

from app.models.finance import FinanceExpenseEntry, FinanceIncomeEntry, FinanceTransferEntry
from app.models.open_finance import OpenFinanceConnection
from app.services.finance import normalize_vendor_key

CUMBUCA_SOURCE = "open_finance"
PLUGGY_SOURCE = "pluggy"

INSTITUTION_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("nubank", "nu pagamentos", "nuconta"), "nubank"),
    (("banco do brasil", "bb "), "banco do brasil"),
    (("itau", "itaú"), "itau"),
    (("bradesco",), "bradesco"),
    (("santander",), "santander"),
    (("inter",), "inter"),
    (("xp ", "xp investimentos"), "xp"),
    (("caixa",), "caixa"),
    (("wise",), "wise"),
)


def _abs_amount(amount: Decimal) -> Decimal:
    return abs(amount).quantize(Decimal("0.01"))


def expense_match_key(tx_date: date | None, amount: Decimal, vendor: str) -> tuple:
    return ("expense", tx_date, _abs_amount(amount), normalize_vendor_key(vendor))


def income_match_key(year: int, month: int, amount: Decimal, description: str) -> tuple:
    return ("income", year, month, _abs_amount(amount), normalize_vendor_key(description))


def existing_cross_provider_expense_keys(
    session: Session,
    user_id: UUID,
    other_source: str,
) -> set[tuple]:
    keys: set[tuple] = set()
    expenses = session.exec(
        select(FinanceExpenseEntry)
        .where(FinanceExpenseEntry.user_id == user_id)
        .where(FinanceExpenseEntry.source == other_source)
    ).all()
    for entry in expenses:
        keys.add(expense_match_key(entry.transaction_date, entry.amount, entry.vendor))

    transfers = session.exec(
        select(FinanceTransferEntry)
        .where(FinanceTransferEntry.user_id == user_id)
        .where(FinanceTransferEntry.source == other_source)
    ).all()
    for entry in transfers:
        keys.add(expense_match_key(entry.transaction_date, entry.amount, entry.description))
    return keys


def existing_cross_provider_income_keys(
    session: Session,
    user_id: UUID,
    other_source: str,
) -> set[tuple]:
    keys: set[tuple] = set()
    incomes = session.exec(
        select(FinanceIncomeEntry)
        .where(FinanceIncomeEntry.user_id == user_id)
        .where(FinanceIncomeEntry.source == other_source)
    ).all()
    for entry in incomes:
        keys.add(income_match_key(entry.year, entry.month, entry.amount, entry.description))
    return keys


def normalize_institution_name(name: str) -> str:
    lowered = (name or "").strip().lower()
    if not lowered:
        return ""
    for aliases, canonical in INSTITUTION_ALIASES:
        if any(alias in lowered for alias in aliases):
            return canonical
    return lowered


def overlapping_institutions(connections: list[OpenFinanceConnection]) -> list[str]:
    """Return canonical institution names present on both Cumbuca and Pluggy."""
    by_provider: dict[str, set[str]] = {}
    for connection in connections:
        if connection.status == "disconnected":
            continue
        name = normalize_institution_name(connection.institution_name)
        if not name or name == "cumbuca open finance":
            continue
        by_provider.setdefault(connection.provider, set()).add(name)
    cumbuca = by_provider.get("cumbuca", set())
    pluggy = by_provider.get("pluggy", set())
    return sorted(cumbuca & pluggy)


def both_providers_connected(connections: list[OpenFinanceConnection]) -> bool:
    providers = {
        connection.provider
        for connection in connections
        if connection.status not in {"disconnected", "inactive"}
        and (connection.provider != "cumbuca" or connection.refresh_token or connection.status == "active")
    }
    return "cumbuca" in providers and "pluggy" in providers
