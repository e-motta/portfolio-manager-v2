"""Pluggy data sync service.

Maps Pluggy API data to app models and provides import preview/confirm flows.
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceInvestmentOpenFinanceImport,
    FinanceTransferEntry,
)
from app.models.investment import Investment
from app.models.open_finance import OpenFinanceConnection
from app.services.pluggy_client import (
    PluggyError,
    fetch_accounts,
    fetch_investments,
    fetch_transactions,
    is_pluggy_available,
    validate_item,
)
from app.services.finance import (
    BILLS_CATEGORY,
    EXPENSE_CATEGORIES,
    PAYMENT_ACCOUNTS,
    load_import_vendor_rule_map,
    normalize_vendor_key,
    resolve_expense_subcategory,
    suggest_expense_category,
    VendorRule,
)
from app.web.helpers import get_investable_asset_types

PLUGGY_SOURCE = "pluggy"
PLUGGY_PROVIDER = "pluggy"

EXCHANGE_TRADED_INVESTMENT_TYPES = frozenset({"EQUITY", "MUTUAL_FUND", "ETF", "STOCK"})

CATEGORY_MAP = {
    "alimentação": "Alimentação fora",
    "alimentacao": "Alimentação fora",
    "restaurante": "Alimentação fora",
    "food": "Alimentação fora",
    "restaurant": "Alimentação fora",
    "supermercado": "Supermercado",
    "groceries": "Supermercado",
    "transporte": "Transporte",
    "transport": "Transporte",
    "travel": "Transporte",
    "lazer": "Bar e lazer",
    "entertainment": "Bar e lazer",
    "moradia": "Casa",
    "home": "Casa",
    "utilities": "Casa",
    "serviços": "Assinaturas digitais",
    "servicos": "Assinaturas digitais",
    "subscription": "Assinaturas digitais",
    "saúde": "Saúde",
    "saude": "Saúde",
    "health": "Saúde",
    "educação": "Profissional",
    "educacao": "Profissional",
    "education": "Profissional",
}

PAYMENT_ACCOUNT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("nubank", "nu pagamentos", "nuconta"), "Nuconta"),
    (("xp",), "XP Crédito"),
    (("banco do brasil", "bb"), "BB Débito"),
    (("caixa",), "Caixa"),
    (("itau", "itaú"), "Itaú"),
    (("bradesco",), "Bradesco"),
    (("santander",), "Santander"),
    (("inter",), "Inter"),
    (("wise",), "Wise"),
)

ASSET_TYPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("poupança", "poupanca", "savings", "cash"), "cash"),
    (("cdb", "lci", "lca", "tesouro", "debenture", "debênture", "fixed", "renda fixa"), "bonds"),
    (("crypto", "bitcoin", "ethereum"), "crypto"),
    (("fii", "real estate", "imóvel", "imovel", "fundo imobiliário"), "real-estate"),
)


@dataclass
class PluggyImportExpenseRow:
    row_key: str
    external_id: str
    year: int
    month: int
    category: str
    vendor: str
    payment_account: str
    amount: Decimal
    transaction_date: date
    already_exists: bool
    selected: bool
    is_reversal: bool = False
    subcategory: str | None = None
    import_kind: str = "expense"
    to_account: str | None = None
    broker: str | None = None
    description: str = ""
    item_id: str = ""


@dataclass
class PluggyImportIncomeRow:
    row_key: str
    external_id: str
    year: int
    month: int
    description: str
    amount: Decimal
    transaction_date: date
    payment_account: str
    already_exists: bool
    selected: bool
    import_kind: str = "income"
    broker: str | None = None
    item_id: str = ""


@dataclass
class PluggyImportInvestmentRow:
    row_key: str
    external_id: str
    institution: str
    name: str
    asset_type_slug: str
    current_value: Decimal
    already_exists: bool
    selected: bool
    is_update: bool
    item_id: str = ""


def get_pluggy_connections(session: Session, user_id: UUID) -> list[OpenFinanceConnection]:
    """Get all Pluggy connections for a user."""
    return list(
        session.exec(
            select(OpenFinanceConnection)
            .where(OpenFinanceConnection.user_id == user_id)
            .where(OpenFinanceConnection.provider == PLUGGY_PROVIDER)
            .where(OpenFinanceConnection.status == "active")
        ).all()
    )


def add_pluggy_connection(
    session: Session,
    user_id: UUID,
    item_id: str,
) -> tuple[OpenFinanceConnection | None, str | None]:
    """Add a new Pluggy connection by item ID.

    Validates the item ID with Pluggy API and stores the connection.
    Returns (connection, None) on success or (None, error_message) on failure.
    """
    if not is_pluggy_available():
        return None, "Pluggy is not configured."

    existing = session.exec(
        select(OpenFinanceConnection)
        .where(OpenFinanceConnection.user_id == user_id)
        .where(OpenFinanceConnection.provider == PLUGGY_PROVIDER)
        .where(OpenFinanceConnection.external_id == item_id)
    ).first()

    if existing:
        return None, "This connection already exists."

    valid, result = validate_item(item_id)
    if not valid:
        return None, str(result)

    item_data = result
    connector = item_data.get("connector", {})
    institution_name = connector.get("institutionName") or connector.get("name") or "Unknown Bank"
    institution_id = str(connector.get("id", "")) if connector.get("id") else None
    status = item_data.get("status", "UNKNOWN")

    connection = OpenFinanceConnection(
        user_id=user_id,
        provider=PLUGGY_PROVIDER,
        external_id=item_id,
        institution_name=institution_name,
        institution_id=institution_id,
        status="active" if status in ("UPDATED", "UPDATING", "WAITING_USER_INPUT") else "inactive",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return connection, None


def remove_pluggy_connection(
    session: Session,
    user_id: UUID,
    connection_id: UUID,
) -> bool:
    """Remove a Pluggy connection."""
    connection = session.exec(
        select(OpenFinanceConnection)
        .where(OpenFinanceConnection.id == connection_id)
        .where(OpenFinanceConnection.user_id == user_id)
        .where(OpenFinanceConnection.provider == PLUGGY_PROVIDER)
    ).first()

    if not connection:
        return False

    session.delete(connection)
    session.commit()
    return True


def refresh_pluggy_connection(
    session: Session,
    connection: OpenFinanceConnection,
) -> tuple[bool, str | None]:
    """Refresh connection status from Pluggy API."""
    valid, result = validate_item(connection.external_id)
    if not valid:
        connection.status = "error"
        connection.updated_at = datetime.utcnow()
        session.add(connection)
        session.commit()
        return False, str(result)

    item_data = result
    connector = item_data.get("connector", {})
    connection.institution_name = connector.get("institutionName") or connector.get("name") or connection.institution_name
    status = item_data.get("status", "UNKNOWN")
    connection.status = "active" if status in ("UPDATED", "UPDATING", "WAITING_USER_INPUT") else "inactive"
    connection.updated_at = datetime.utcnow()
    session.add(connection)
    session.commit()
    return True, None


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
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


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)
    today = date.today()
    if end > today:
        end = today
    if end < start:
        end = start
    return start, end


def map_payment_account(institution_name: str, account_type: str = "") -> str:
    """Map Pluggy institution/account to app payment account."""
    haystack = f"{institution_name} {account_type}".lower()
    for keywords, payment_account in PAYMENT_ACCOUNT_RULES:
        if any(keyword in haystack for keyword in keywords):
            return payment_account
    return "Nuconta"


def map_category(pluggy_category: str | None, description: str) -> str:
    """Map Pluggy category to app expense category."""
    normalized = (pluggy_category or "").strip().lower()
    if normalized in CATEGORY_MAP:
        return CATEGORY_MAP[normalized]
    for keyword, category in CATEGORY_MAP.items():
        if keyword in normalized:
            return category
    description_lower = description.lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in description_lower:
            return category
    return "Outros"


def map_asset_type_slug(investment: dict[str, Any]) -> str:
    """Map Pluggy investment type to app asset type slug."""
    haystack = " ".join(
        str(investment.get(key, "") or "")
        for key in ("type", "subtype", "name")
    ).lower()
    for keywords, slug in ASSET_TYPE_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return slug
    return "bonds"


def is_exchange_traded_investment(investment: dict[str, Any]) -> bool:
    """Check if investment is exchange-traded (should be in Securities, not Other Investments)."""
    inv_type = str(investment.get("type", "")).upper()
    subtype = str(investment.get("subtype", "")).upper()
    return inv_type in EXCHANGE_TRADED_INVESTMENT_TYPES or subtype in EXCHANGE_TRADED_INVESTMENT_TYPES


def _existing_pluggy_expense_ids(session: Session, user_id: UUID) -> set[str]:
    rows = session.exec(
        select(FinanceExpenseEntry.external_id)
        .where(FinanceExpenseEntry.user_id == user_id)
        .where(FinanceExpenseEntry.source == PLUGGY_SOURCE)
        .where(FinanceExpenseEntry.external_id.is_not(None))
    ).all()
    return {row for row in rows if row}


def _existing_pluggy_income_ids(session: Session, user_id: UUID) -> set[str]:
    rows = session.exec(
        select(FinanceIncomeEntry.external_id)
        .where(FinanceIncomeEntry.user_id == user_id)
        .where(FinanceIncomeEntry.source == PLUGGY_SOURCE)
        .where(FinanceIncomeEntry.external_id.is_not(None))
    ).all()
    return {row for row in rows if row}


def _existing_pluggy_transfer_ids(session: Session, user_id: UUID) -> set[str]:
    rows = session.exec(
        select(FinanceTransferEntry.external_id)
        .where(FinanceTransferEntry.user_id == user_id)
        .where(FinanceTransferEntry.source == PLUGGY_SOURCE)
        .where(FinanceTransferEntry.external_id.is_not(None))
    ).all()
    return {row for row in rows if row}


def _existing_pluggy_investment_import_ids(session: Session, user_id: UUID) -> set[str]:
    rows = session.exec(
        select(FinanceInvestmentOpenFinanceImport.external_id)
        .where(FinanceInvestmentOpenFinanceImport.user_id == user_id)
    ).all()
    return {row for row in rows if row and row.startswith("pluggy:")}


def _existing_investment_map(session: Session) -> dict[str, Investment]:
    from app.web.helpers import get_investments
    investments = get_investments(session)
    return {
        investment.external_id: investment
        for investment in investments
        if investment.external_id and investment.external_id.startswith("pluggy:")
    }


def build_pluggy_expense_import_rows(
    session: Session,
    user_id: UUID,
    connections: list[OpenFinanceConnection],
    *,
    year: int,
    month: int,
) -> tuple[list[PluggyImportExpenseRow], list[str]]:
    """Build expense import rows from Pluggy transactions."""
    warnings: list[str] = []
    rows: list[PluggyImportExpenseRow] = []

    if not connections:
        return rows, ["No Pluggy connections found."]

    existing_ids = (
        _existing_pluggy_expense_ids(session, user_id)
        | _existing_pluggy_transfer_ids(session, user_id)
        | _existing_pluggy_investment_import_ids(session, user_id)
    )
    vendor_rules = load_import_vendor_rule_map(session, user_id)
    start_date, end_date = _month_bounds(year, month)

    for connection in connections:
        try:
            accounts = fetch_accounts(connection.external_id)
        except PluggyError as exc:
            warnings.append(f"{connection.institution_name}: {exc}")
            continue

        for account in accounts:
            account_id = account.get("id")
            account_type = account.get("type", "")
            if not account_id:
                continue

            if account_type == "CREDIT":
                continue

            try:
                transactions = fetch_transactions(account_id, from_date=start_date, to_date=end_date)
            except PluggyError as exc:
                warnings.append(f"{connection.institution_name} ({account.get('name', 'account')}): {exc}")
                continue

            payment_account = map_payment_account(connection.institution_name, account_type)

            for tx in transactions:
                row = _normalize_pluggy_expense_transaction(
                    tx,
                    connection,
                    payment_account,
                    year,
                    month,
                    vendor_rules,
                )
                if row is None:
                    continue
                row.already_exists = row.external_id in existing_ids
                row.selected = not row.already_exists
                rows.append(row)

    rows.sort(key=lambda r: (r.transaction_date, r.vendor))
    return rows, warnings


def _normalize_pluggy_expense_transaction(
    tx: dict[str, Any],
    connection: OpenFinanceConnection,
    payment_account: str,
    year: int,
    month: int,
    vendor_rules: dict[str, VendorRule] | None = None,
) -> PluggyImportExpenseRow | None:
    """Normalize a Pluggy transaction to an expense import row."""
    external_id = f"pluggy:{tx.get('id', '')}"
    if not tx.get("id"):
        return None

    amount_raw = _parse_decimal(tx.get("amount"))
    if amount_raw is None or amount_raw == 0:
        return None

    if amount_raw > 0:
        return None

    tx_date = _parse_date(tx.get("date"))
    if tx_date is None:
        return None

    description = str(tx.get("description") or "").strip()
    vendor = description or "Unknown"
    pluggy_category = tx.get("category")
    vendor_key = normalize_vendor_key(vendor)
    saved_rule = (vendor_rules or {}).get(vendor_key)
    saved_category = saved_rule[0] if saved_rule else None

    if saved_category in EXPENSE_CATEGORIES:
        category = saved_category
    else:
        category = map_category(pluggy_category, vendor)
        if category == "Outros":
            suggested = suggest_expense_category(vendor)
            if suggested != "Outros":
                category = suggested
    if category not in EXPENSE_CATEGORIES:
        category = "Outros"

    if payment_account not in PAYMENT_ACCOUNTS:
        payment_account = "Nuconta"

    subcategory = None
    row_description = ""
    if saved_rule:
        row_description = saved_rule[2] if len(saved_rule) > 2 else ""
    if category == BILLS_CATEGORY:
        subcategory = resolve_expense_subcategory(
            category,
            vendor,
            vendor_rules or {},
        )

    return PluggyImportExpenseRow(
        row_key=external_id,
        external_id=external_id,
        year=tx_date.year if tx_date.month == month and tx_date.year == year else year,
        month=tx_date.month if tx_date.month == month else month,
        category=category,
        vendor=vendor,
        payment_account=payment_account,
        amount=amount_raw,
        transaction_date=tx_date,
        already_exists=False,
        selected=True,
        is_reversal=False,
        subcategory=subcategory,
        description=row_description,
        item_id=connection.external_id,
    )


def build_pluggy_income_import_rows(
    session: Session,
    user_id: UUID,
    connections: list[OpenFinanceConnection],
    *,
    year: int,
    month: int,
) -> tuple[list[PluggyImportIncomeRow], list[str]]:
    """Build income import rows from Pluggy transactions (credits)."""
    warnings: list[str] = []
    rows: list[PluggyImportIncomeRow] = []

    if not connections:
        return rows, ["No Pluggy connections found."]

    existing_ids = (
        _existing_pluggy_income_ids(session, user_id)
        | _existing_pluggy_investment_import_ids(session, user_id)
    )
    start_date, end_date = _month_bounds(year, month)

    for connection in connections:
        try:
            accounts = fetch_accounts(connection.external_id)
        except PluggyError as exc:
            warnings.append(f"{connection.institution_name}: {exc}")
            continue

        for account in accounts:
            account_id = account.get("id")
            account_type = account.get("type", "")
            if not account_id or account_type == "CREDIT":
                continue

            try:
                transactions = fetch_transactions(account_id, from_date=start_date, to_date=end_date)
            except PluggyError as exc:
                warnings.append(f"{connection.institution_name} ({account.get('name', 'account')}): {exc}")
                continue

            payment_account = map_payment_account(connection.institution_name, account_type)

            for tx in transactions:
                row = _normalize_pluggy_income_transaction(tx, connection, payment_account)
                if row is None:
                    continue
                if row.transaction_date.month != month or row.transaction_date.year != year:
                    continue
                row.already_exists = row.external_id in existing_ids
                row.selected = not row.already_exists
                rows.append(row)

    rows.sort(key=lambda r: (r.transaction_date, r.description))
    return rows, warnings


def _normalize_pluggy_income_transaction(
    tx: dict[str, Any],
    connection: OpenFinanceConnection,
    payment_account: str,
) -> PluggyImportIncomeRow | None:
    """Normalize a Pluggy transaction to an income import row."""
    external_id = f"pluggy:{tx.get('id', '')}"
    if not tx.get("id"):
        return None

    amount_raw = _parse_decimal(tx.get("amount"))
    if amount_raw is None or amount_raw <= 0:
        return None

    tx_date = _parse_date(tx.get("date"))
    if tx_date is None:
        return None

    description = str(tx.get("description") or "").strip() or "Unknown"

    if payment_account not in PAYMENT_ACCOUNTS:
        payment_account = "Nuconta"

    return PluggyImportIncomeRow(
        row_key=external_id,
        external_id=external_id,
        year=tx_date.year,
        month=tx_date.month,
        description=description,
        amount=amount_raw,
        transaction_date=tx_date,
        payment_account=payment_account,
        already_exists=False,
        selected=True,
        item_id=connection.external_id,
    )


def build_pluggy_investment_import_rows(
    session: Session,
    connections: list[OpenFinanceConnection],
) -> tuple[list[PluggyImportInvestmentRow], list[str]]:
    """Build investment import rows from Pluggy investments."""
    warnings: list[str] = []
    rows: list[PluggyImportInvestmentRow] = []

    if not connections:
        return rows, ["No Pluggy connections found."]

    asset_types = get_investable_asset_types(session)
    slug_by_name = {at.slug: at.slug for at in asset_types}
    name_to_slug = {at.name.lower(): at.slug for at in asset_types}
    slug_by_name.update(name_to_slug)

    existing = _existing_investment_map(session)

    for connection in connections:
        try:
            investments = fetch_investments(connection.external_id)
        except PluggyError as exc:
            warnings.append(f"{connection.institution_name}: {exc}")
            continue

        for inv in investments:
            row = _normalize_pluggy_investment(inv, connection, slug_by_name)
            if row is None:
                continue

            if row.external_id in existing:
                row.already_exists = True
                row.is_update = True
                row.selected = True
            rows.append(row)

    rows.sort(key=lambda r: (r.institution, r.name))
    return rows, warnings


def _normalize_pluggy_investment(
    inv: dict[str, Any],
    connection: OpenFinanceConnection,
    slug_by_name: dict[str, str],
) -> PluggyImportInvestmentRow | None:
    """Normalize a Pluggy investment to an import row."""
    if is_exchange_traded_investment(inv):
        return None

    inv_id = inv.get("id")
    if not inv_id:
        return None

    external_id = f"pluggy:{inv_id}"

    balance = _parse_decimal(inv.get("value") or inv.get("balance") or inv.get("amount"))
    if balance is None or balance < 0:
        return None

    slug = map_asset_type_slug(inv)
    if slug not in slug_by_name:
        slug = "bonds"

    institution = connection.institution_name
    name = str(inv.get("name") or inv.get("productName") or "Investment").strip()

    return PluggyImportInvestmentRow(
        row_key=external_id,
        external_id=external_id,
        institution=institution,
        name=name,
        asset_type_slug=slug,
        current_value=balance,
        already_exists=False,
        selected=True,
        is_update=False,
        item_id=connection.external_id,
    )


def update_connection_last_synced(
    session: Session,
    connection: OpenFinanceConnection,
) -> None:
    """Update the last_synced_at timestamp for a connection."""
    connection.last_synced_at = datetime.utcnow()
    connection.updated_at = datetime.utcnow()
    session.add(connection)
    session.commit()
