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
    PaginationCapWarning,
    PluggyError,
    fetch_accounts,
    fetch_investments,
    fetch_transactions,
    is_pluggy_available,
    validate_item,
)
from app.models.asset_type import AssetType
from app.models.portfolio import Portfolio
from app.services.finance import (
    BILLS_CATEGORY,
    EXPENSE_CATEGORIES,
    PAYMENT_ACCOUNTS,
    TRANSFER_ACCOUNTS,
    load_import_vendor_rule_map,
    normalize_vendor_key,
    resolve_expense_subcategory,
    suggest_expense_category,
    suggest_investment_broker,
    VendorRule,
)
from app.services.open_finance_match import (
    CUMBUCA_SOURCE,
    expense_match_key,
    existing_cross_provider_expense_keys,
    existing_cross_provider_income_keys,
    income_match_key,
)
from app.web.helpers import get_investable_asset_types

PLUGGY_SOURCE = "pluggy"
PLUGGY_PROVIDER = "pluggy"

ACTIVE_ITEM_STATUSES = frozenset({"UPDATED", "UPDATING"})
NEEDS_ATTENTION_ITEM_STATUSES = frozenset({
    "WAITING_USER_INPUT",
    "LOGIN_ERROR",
    "OUTDATED",
})
SYNCABLE_CONNECTION_STATUSES = frozenset({"active", "needs_attention"})

# Own-account transfers only. Do not substring-match "pix"/"ted" — ordinary
# Pix purchases are often categorized as "Transfer - PIX".
OWN_ACCOUNT_TRANSFER_CATEGORIES = frozenset({
    "same person transfer",
    "same person transfer - cash",
    "same person transfer - pix",
    "same person transfer - ted",
    "transfer - internal",
    "transferência entre a mesma pessoa",
    "transferencia entre a mesma pessoa",
    "transferência entre a mesma pessoa - dinheiro",
    "transferencia entre a mesma pessoa - dinheiro",
    "transferência entre a mesma pessoa - pix",
    "transferencia entre a mesma pessoa - pix",
    "transferência entre a mesma pessoa - ted",
    "transferencia entre a mesma pessoa - ted",
    "transferência - interna",
    "transferencia - interna",
})
OWN_ACCOUNT_TRANSFER_CATEGORY_IDS = frozenset({
    "04000000",  # Same person transfer
    "04010000",  # Same person transfer - Cash
    "04020000",  # Same person transfer - PIX
    "04030000",  # Same person transfer - TED
    "05060000",  # Transfer - Internal
})
INVESTMENT_CATEGORIES = frozenset({
    "investment",
    "investments",
    "investimento",
    "investimentos",
    "application",
    "aplicação",
    "aplicacao",
    "redemption",
    "resgate",
})
TRANSFER_VENDOR_KEYWORDS = (
    "transferencia",
    "transferência",
    "transf ",
    "ted ",
    "doc ",
    "pix enviado",
    "entre contas",
)
BILL_PAYMENT_CATEGORIES = frozenset({
    "credit card payment",
    "pagamento com cartão de crédito",
    "pagamento com cartao de credito",
})
BILL_PAYMENT_CATEGORY_IDS = frozenset({
    "05090000",  # Credit card payment
})
BILL_PAYMENT_KEYWORDS = (
    "pagamento de fatura",
    "pagamento da fatura",
    "pagamento fatura",
    "pagamento cartao",
    "pagamento cartão",
    "fatura cartao",
    "fatura cartão",
    "fatura do cartao",
    "fatura do cartão",
    "credit card payment",
    "card bill payment",
    "pagamento recebido",
)
CREDIT_PAYMENT_ACCOUNT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("nubank", "nu pagamentos"), "Nubank"),
    (("xp",), "XP Crédito"),
    (("banco do brasil", "bb"), "BB Crédito"),
)

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
    likely_duplicate: bool = False
    is_bill_payment: bool = False
    account_type: str = ""


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
    likely_duplicate: bool = False


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


def map_pluggy_item_status(pluggy_status: str) -> str:
    """Map a Pluggy item status to a connection status.

    UPDATED/UPDATING are active. WAITING_USER_INPUT, LOGIN_ERROR, and
    OUTDATED need attention. Everything else is inactive.
    """
    status = (pluggy_status or "").upper()
    if status in ACTIVE_ITEM_STATUSES:
        return "active"
    if status in NEEDS_ATTENTION_ITEM_STATUSES:
        return "needs_attention"
    return "inactive"


def get_pluggy_connections(session: Session, user_id: UUID) -> list[OpenFinanceConnection]:
    """Get Pluggy connections that can still be listed or synced."""
    return list(
        session.exec(
            select(OpenFinanceConnection)
            .where(OpenFinanceConnection.user_id == user_id)
            .where(OpenFinanceConnection.provider == PLUGGY_PROVIDER)
            .where(OpenFinanceConnection.status != "disconnected")
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
        status=map_pluggy_item_status(status),
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
    connection.status = map_pluggy_item_status(status)
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
    rules = CREDIT_PAYMENT_ACCOUNT_RULES if account_type.upper() == "CREDIT" else PAYMENT_ACCOUNT_RULES
    for keywords, payment_account in rules:
        if any(keyword in haystack for keyword in keywords):
            return payment_account
    return "Nubank" if account_type.upper() == "CREDIT" else "Nuconta"


def _haystacks(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    normalized = lowered.replace(" de ", " ").replace(" da ", " ")
    if normalized == lowered:
        return (lowered,)
    return (lowered, normalized)


def _pluggy_category_fields(tx: dict[str, Any]) -> tuple[str, str]:
    category = str(tx.get("category") or "").strip()
    category_id = str(tx.get("categoryId") or tx.get("category_id") or "").strip()
    return category, category_id


def is_own_account_transfer(tx: dict[str, Any]) -> bool:
    """True when Pluggy labels the row as a transfer between the user's own accounts."""
    category, category_id = _pluggy_category_fields(tx)
    if category_id and category_id in OWN_ACCOUNT_TRANSFER_CATEGORY_IDS:
        return True
    return category.lower() in OWN_ACCOUNT_TRANSFER_CATEGORIES


def is_bill_payment_category(tx: dict[str, Any]) -> bool:
    category, category_id = _pluggy_category_fields(tx)
    if category_id and category_id in BILL_PAYMENT_CATEGORY_IDS:
        return True
    return category.lower() in BILL_PAYMENT_CATEGORIES


def is_bill_payment_description(description: str) -> bool:
    return any(
        keyword in haystack
        for haystack in _haystacks(description)
        for keyword in BILL_PAYMENT_KEYWORDS
    )


def is_bill_payment(tx: dict[str, Any], description: str) -> bool:
    """Prefer Pluggy's credit-card-payment category; fall back to keywords."""
    if is_bill_payment_category(tx):
        return True
    return is_bill_payment_description(description)


def suggest_pluggy_debit_import_kind(tx: dict[str, Any], vendor: str) -> str:
    """Default classification from Pluggy category/type and description."""
    category = str(tx.get("category") or "").strip().lower()
    if category in INVESTMENT_CATEGORIES or any(token in category for token in INVESTMENT_CATEGORIES):
        return "investment"
    if is_own_account_transfer(tx):
        return "transfer"
    if is_bill_payment(tx, vendor):
        return "transfer"
    for haystack in _haystacks(vendor):
        if any(keyword in haystack for keyword in TRANSFER_VENDOR_KEYWORDS):
            return "transfer"
    return "expense"


def suggest_pluggy_credit_import_kind(tx: dict[str, Any], description: str) -> str:
    category = str(tx.get("category") or "").strip().lower()
    if category in INVESTMENT_CATEGORIES or any(token in category for token in INVESTMENT_CATEGORIES):
        return "investment"
    if is_own_account_transfer(tx):
        return "income"
    return "income"


def suggest_transfer_to_account(vendor: str, from_account: str) -> str | None:
    haystack = vendor.lower()
    for keywords, payment_account in PAYMENT_ACCOUNT_RULES + CREDIT_PAYMENT_ACCOUNT_RULES:
        if payment_account == from_account:
            continue
        if payment_account not in TRANSFER_ACCOUNTS:
            continue
        if any(keyword in haystack for keyword in keywords):
            return payment_account
    defaults = {
        "Nuconta": "Nubank",
        "Nubank": "Nuconta",
        "BB Débito": "Nuconta",
        "Wise": "Nuconta",
    }
    suggested = defaults.get(from_account)
    if suggested and suggested != from_account:
        return suggested
    for account in TRANSFER_ACCOUNTS:
        if account != from_account:
            return account
    return None


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


def _existing_investment_map(session: Session, user_id: UUID) -> dict[str, Investment]:
    """Get existing Pluggy investments for a user's portfolio only."""
    investments = session.exec(
        select(Investment)
        .join(AssetType)
        .join(Portfolio)
        .where(Portfolio.user_id == user_id)
        .where(AssetType.is_exchange_traded.is_(False))  # type: ignore[attr-defined]
    ).all()
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
    """Build expense import rows from Pluggy bank and credit-card transactions.

    Credit card purchases are imported individually as expenses using the
    purchase date (or the installment charge date). Bank-account bill
    payments for those cards are classified as transfers and left
    unselected so the purchase and the bill settlement are not both
    counted as expenses.
    """
    warnings: list[str] = []
    rows: list[PluggyImportExpenseRow] = []

    if not connections:
        return rows, ["No Pluggy connections found."]

    existing_ids = (
        _existing_pluggy_expense_ids(session, user_id)
        | _existing_pluggy_transfer_ids(session, user_id)
        | _existing_pluggy_investment_import_ids(session, user_id)
    )
    cross_keys = existing_cross_provider_expense_keys(session, user_id, CUMBUCA_SOURCE)
    vendor_rules = load_import_vendor_rule_map(session, user_id)
    start_date, end_date = _month_bounds(year, month)

    for connection in connections:
        if connection.status not in SYNCABLE_CONNECTION_STATUSES:
            continue
        try:
            accounts = fetch_accounts(connection.external_id)
            warnings.extend(PaginationCapWarning.pop_all())
        except PluggyError as exc:
            warnings.append(f"{connection.institution_name}: {exc}")
            continue

        for account in accounts:
            account_id = account.get("id")
            account_type = str(account.get("type") or "")
            if not account_id:
                continue

            try:
                transactions = fetch_transactions(account_id, from_date=start_date, to_date=end_date)
                warnings.extend(PaginationCapWarning.pop_all())
            except PluggyError as exc:
                warnings.append(f"{connection.institution_name} ({account.get('name', 'account')}): {exc}")
                continue

            payment_account = map_payment_account(connection.institution_name, account_type)

            for tx in transactions:
                row = _normalize_pluggy_expense_transaction(
                    tx,
                    connection,
                    payment_account,
                    account_type,
                    year,
                    month,
                    vendor_rules,
                )
                if row is None:
                    continue
                row.already_exists = row.external_id in existing_ids
                row.likely_duplicate = (
                    not row.already_exists
                    and expense_match_key(row.transaction_date, row.amount, row.vendor) in cross_keys
                )
                row.selected = not row.already_exists and not row.likely_duplicate and not row.is_bill_payment
                rows.append(row)

    rows.sort(key=lambda r: (r.transaction_date, r.vendor))
    return rows, warnings


def _credit_card_purchase_date(tx: dict[str, Any]) -> date | None:
    """Prefer the purchase date, then the installment charge date."""
    metadata = tx.get("creditCardMetadata") or tx.get("credit_card_metadata") or {}
    if isinstance(metadata, dict):
        purchase = _parse_date(metadata.get("purchaseDate") or metadata.get("purchase_date"))
        if purchase is not None:
            return purchase
    return _parse_date(tx.get("date"))


def _normalize_pluggy_expense_transaction(
    tx: dict[str, Any],
    connection: OpenFinanceConnection,
    payment_account: str,
    account_type: str,
    year: int,
    month: int,
    vendor_rules: dict[str, VendorRule] | None = None,
) -> PluggyImportExpenseRow | None:
    """Normalize a Pluggy bank or credit-card transaction to an import row.

    Real Nubank CREDIT accounts send purchases as ``type=DEBIT`` with a
    *positive* amount and refunds/payments as ``type=CREDIT`` with a
    *negative* amount. Classification follows ``type`` regardless of sign:

    - DEBIT: purchase, stored as a negative expense
    - CREDIT + bill payment (Pluggy category ``Credit card payment``, then
      keywords): skip — the settlement is not an expense
    - CREDIT otherwise: refund, stored as a positive expense with
      ``is_reversal=True`` (Cumbuca convention: ``amount > 0`` offsets spend)
    """
    external_id = f"pluggy:{tx.get('id', '')}"
    if not tx.get("id"):
        return None

    amount_raw = _parse_decimal(tx.get("amount"))
    if amount_raw is None or amount_raw == 0:
        return None

    is_credit_account = account_type.upper() == "CREDIT"
    tx_type = str(tx.get("type") or "").upper()
    description = str(tx.get("description") or "").strip()
    vendor = description or "Unknown"
    bill_payment = is_bill_payment(tx, vendor)

    if is_credit_account:
        if bill_payment:
            return None
        tx_date = _credit_card_purchase_date(tx)
        if tx_type == "CREDIT":
            is_reversal = True
            amount = abs(amount_raw)
        elif tx_type == "DEBIT":
            is_reversal = False
            amount = -abs(amount_raw)
        else:
            return None
        import_kind = "expense"
        to_account = None
        broker = None
    else:
        if amount_raw > 0:
            return None
        tx_date = _parse_date(tx.get("date"))
        is_reversal = False
        amount = amount_raw
        import_kind = suggest_pluggy_debit_import_kind(tx, vendor)
        to_account = suggest_transfer_to_account(vendor, payment_account) if import_kind == "transfer" else None
        broker = suggest_investment_broker(payment_account, vendor) if import_kind == "investment" else None

    if tx_date is None:
        return None

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
        payment_account = "Nubank" if is_credit_account else "Nuconta"

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
        amount=amount,
        transaction_date=tx_date,
        already_exists=False,
        selected=True,
        is_reversal=is_reversal,
        subcategory=subcategory,
        import_kind=import_kind,
        to_account=to_account,
        broker=broker,
        description=row_description,
        item_id=connection.external_id,
        is_bill_payment=bill_payment and not is_credit_account,
        account_type=account_type,
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
    cross_keys = existing_cross_provider_income_keys(session, user_id, CUMBUCA_SOURCE)
    start_date, end_date = _month_bounds(year, month)

    for connection in connections:
        if connection.status not in SYNCABLE_CONNECTION_STATUSES:
            continue
        try:
            accounts = fetch_accounts(connection.external_id)
            warnings.extend(PaginationCapWarning.pop_all())
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
                warnings.extend(PaginationCapWarning.pop_all())
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
                row.likely_duplicate = (
                    not row.already_exists
                    and income_match_key(row.year, row.month, row.amount, row.description) in cross_keys
                )
                leave_unselected = row.import_kind != "income" or row.likely_duplicate
                row.selected = not row.already_exists and not leave_unselected
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

    import_kind = suggest_pluggy_credit_import_kind(tx, description)
    broker = suggest_investment_broker(payment_account, description) if import_kind == "investment" else None

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
        import_kind=import_kind,
        broker=broker,
        item_id=connection.external_id,
    )


def build_pluggy_investment_import_rows(
    session: Session,
    user_id: UUID,
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

    existing = _existing_investment_map(session, user_id)

    for connection in connections:
        if connection.status not in SYNCABLE_CONNECTION_STATUSES:
            continue
        try:
            investments = fetch_investments(connection.external_id)
            warnings.extend(PaginationCapWarning.pop_all())
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
