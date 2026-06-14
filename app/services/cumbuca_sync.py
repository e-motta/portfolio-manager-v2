import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Session, select

from fastapi import HTTPException

from app.models.finance import FinanceExpenseEntry, FinanceIncomeEntry
from app.models.investment import Investment
from app.models.user import User
from app.services.cumbuca_mcp import (
    CumbucaMcpError,
    fetch_all_transactions,
    fetch_investments,
)
from app.services.cumbuca_oauth import OPEN_FINANCE_SOURCE, refresh_access_token
from app.services.finance import (
    BILLS_CATEGORY,
    EXPENSE_CATEGORIES,
    PAYMENT_ACCOUNTS,
    load_vendor_rule_map,
    normalize_vendor_key,
    resolve_expense_subcategory,
    save_vendor_category,
    suggest_expense_category,
)
from app.web.helpers import get_investable_asset_types, get_investments

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

EXCHANGE_TRADED_INVESTMENT_TYPES = frozenset({"EQUITY", "ETF", "SECURITY"})

CATEGORY_MAP = {
    "alimentação": "Alimentação fora",
    "alimentacao": "Alimentação fora",
    "restaurante": "Alimentação fora",
    "supermercado": "Supermercado",
    "transporte": "Transporte",
    "lazer": "Bar e lazer",
    "moradia": "Casa",
    "serviços": "Assinaturas digitais",
    "servicos": "Assinaturas digitais",
    "saúde": "Saúde",
    "saude": "Saúde",
    "educação": "Profissional",
    "educacao": "Profissional",
}

PAYMENT_ACCOUNT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("nubank", "ultraviolet"), "Nubank"),
    (("xp", "xpcredito", "xp crédito", "xp credito"), "XP Crédito"),
    (("ourocard", "bb crédito", "bb credito"), "BB Crédito"),
    (("nu pagamentos", "nuconta", "conta_pagamento"), "Nuconta"),
    (("banco do brasil", "bb débito", "bb debito", "checking"), "BB Débito"),
    (("wise",), "Wise"),
)

INVESTMENT_TRANSACTION_TYPES = frozenset(
    {
        "RESGATE_APLIC_FINANCEIRA",
        "APLICACAO",
        "APLICACAO_FINANCEIRA",
    }
)

ASSET_TYPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("poupança", "poupanca", "savings", "cash"), "cash"),
    (("cdb", "lci", "lca", "tesouro", "debenture", "debênture", "fixed"), "bonds"),
    (("crypto", "bitcoin"), "crypto"),
    (("fii", "real estate", "imóvel", "imovel"), "real-estate"),
)


@dataclass
class ImportExpenseRow:
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


@dataclass
class ImportIncomeRow:
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


@dataclass
class ImportInvestmentRow:
    row_key: str
    external_id: str
    institution: str
    name: str
    asset_type_slug: str
    current_value: Decimal
    already_exists: bool
    selected: bool
    is_update: bool


@dataclass
class StashedFinanceImport:
    rows: list[ImportExpenseRow]


@dataclass
class StashedIncomeImport:
    rows: list[ImportIncomeRow]


@dataclass
class StashedInvestmentImport:
    rows: list[ImportInvestmentRow]


_finance_stash: dict[str, StashedFinanceImport] = {}
_income_stash: dict[str, StashedIncomeImport] = {}
_investment_stash: dict[str, StashedInvestmentImport] = {}


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def use_fixture_mode() -> bool:
    import os

    return os.environ.get("TESTING") == "1"


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


def map_payment_account(account: dict[str, Any], *, source_kind: str = "bank") -> str:
    if source_kind == "credit_card":
        return map_payment_account_from_brand(str(account.get("brandName") or ""), "Nubank")

    haystack = " ".join(
        str(account.get(key, "") or "")
        for key in (
            "bank",
            "name",
            "subtype",
            "type",
            "brand",
            "brandName",
        )
    ).lower()
    for keywords, payment_account in PAYMENT_ACCOUNT_RULES:
        if any(keyword in haystack for keyword in keywords):
            return payment_account
    if "CREDIT" in str(account.get("type", "")).upper():
        return "Nubank"
    return "Nuconta"


def map_payment_account_from_brand(brand: str, default: str) -> str:
    lowered = brand.lower()
    for keywords, payment_account in PAYMENT_ACCOUNT_RULES:
        if any(keyword in lowered for keyword in keywords):
            return payment_account
    return default


def map_category(raw_category: str | None, description: str) -> str:
    normalized = (raw_category or "").strip().lower()
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
    haystack = " ".join(
        str(investment.get(key, "") or "")
        for key in ("type", "subtype", "name", "category")
    ).lower()
    for keywords, slug in ASSET_TYPE_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return slug
    return "bonds"


def is_exchange_traded_investment(investment: dict[str, Any]) -> bool:
    investment_type = str(investment.get("type", "")).upper()
    return investment_type in EXCHANGE_TRADED_INVESTMENT_TYPES


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1).isoformat()
    end = date(year, month, last_day).isoformat()
    return start, end


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _expense_period_for_import(
    source_kind: str,
    import_year: int,
    import_month: int,
) -> tuple[int, int]:
    if source_kind == "credit_card":
        return _previous_month(import_year, import_month)
    return import_year, import_month


def _row_matches_import(
    row: ImportExpenseRow,
    tx: dict[str, Any],
    import_year: int,
    import_month: int,
) -> bool:
    source_kind = str(tx.get("_source_kind") or "bank")
    target_year, target_month = _expense_period_for_import(
        source_kind, import_year, import_month
    )
    return row.year == target_year and row.month == target_month


def _existing_expense_ids(session: Session, user_id: UUID) -> set[str]:
    rows = session.exec(
        select(FinanceExpenseEntry.external_id)
        .where(FinanceExpenseEntry.user_id == user_id)
        .where(FinanceExpenseEntry.source == OPEN_FINANCE_SOURCE)
        .where(FinanceExpenseEntry.external_id.is_not(None))  # type: ignore[union-attr]
    ).all()
    return {row for row in rows if row}


def _existing_income_ids(session: Session, user_id: UUID) -> set[str]:
    rows = session.exec(
        select(FinanceIncomeEntry.external_id)
        .where(FinanceIncomeEntry.user_id == user_id)
        .where(FinanceIncomeEntry.source == OPEN_FINANCE_SOURCE)
        .where(FinanceIncomeEntry.external_id.is_not(None))  # type: ignore[union-attr]
    ).all()
    return {row for row in rows if row}


def _existing_investment_map(session: Session) -> dict[str, Investment]:
    investments = get_investments(session)
    return {
        investment.external_id: investment
        for investment in investments
        if investment.external_id
    }


def _parse_money_field(value: Any) -> tuple[Decimal | None, str | None]:
    if isinstance(value, dict):
        currency = str(value.get("currency") or "BRL").upper()
        return _parse_decimal(value.get("amount")), currency
    if value is None:
        return None, None
    return _parse_decimal(value), "BRL"


def _transaction_amount(tx: dict[str, Any]) -> Decimal | None:
    for key in ("brazilianAmount", "BrazilianAmount"):
        amount, _currency = _parse_money_field(tx.get(key))
        if amount is not None:
            return amount

    for key in ("transactionAmount", "amount"):
        amount, currency = _parse_money_field(tx.get(key))
        if amount is None:
            continue
        if currency in ("BRL", ""):
            return amount

    return None


def _is_ignored_credit_card_transaction(tx: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(tx.get(key) or "")
        for key in ("transactionName", "description", "merchant", "transactionType")
    ).lower()
    return "pagamento recebido" in haystack


def _transaction_vendor(tx: dict[str, Any]) -> str:
    name = str(
        tx.get("transactionName")
        or tx.get("description")
        or tx.get("merchant")
        or "Unknown"
    ).strip()
    if "|" in name:
        name = name.split("|", 1)[1].strip()
    return name or "Unknown"


def _normalize_expense_transaction(
    tx: dict[str, Any],
    account_lookup: dict[str, dict[str, Any]],
    *,
    source_kind: str,
    vendor_rules: dict[str, tuple[str, str | None]] | None = None,
) -> ImportExpenseRow | None:
    if str(tx.get("_source_kind") or "bank") != source_kind:
        return None

    if source_kind == "credit_card" and _is_ignored_credit_card_transaction(tx):
        return None

    external_id = str(tx.get("transactionId") or tx.get("id") or "")
    if not external_id:
        return None

    credit_debit = str(tx.get("creditDebitType", "DEBITO")).upper()
    is_reversal = source_kind == "credit_card" and credit_debit == "CREDITO"
    if not is_reversal and credit_debit != "DEBITO":
        return None

    tx_type = str(tx.get("type") or "").upper()
    if tx_type in INVESTMENT_TRANSACTION_TYPES:
        return None

    amount_raw = _transaction_amount(tx)
    if amount_raw is None or amount_raw <= 0:
        return None
    amount = abs(amount_raw) if is_reversal else -abs(amount_raw)

    tx_date = _parse_date(tx.get("transactionDateTime") or tx.get("transactionDate"))
    if tx_date is None:
        return None

    source_account = tx.get("_source_account")
    if isinstance(source_account, dict):
        account = source_account
    else:
        account_id = str(tx.get("accountId") or tx.get("account_id") or "")
        account = account_lookup.get(account_id, {})

    vendor = _transaction_vendor(tx)
    vendor_key = normalize_vendor_key(vendor)
    saved_rule = (vendor_rules or {}).get(vendor_key)
    saved_category = saved_rule[0] if saved_rule else None
    if saved_category in EXPENSE_CATEGORIES:
        category = saved_category
    else:
        category = map_category(str(tx.get("category") or ""), vendor)
        if category == "Outros":
            suggested = suggest_expense_category(vendor)
            if suggested != "Outros":
                category = suggested
    if category not in EXPENSE_CATEGORIES:
        category = "Outros"
    payment_account = map_payment_account(account, source_kind=source_kind)
    if payment_account not in PAYMENT_ACCOUNTS:
        payment_account = "Nuconta"

    row_year = tx_date.year
    row_month = tx_date.month
    if source_kind == "credit_card":
        statement_year = tx.get("_statement_year")
        statement_month = tx.get("_statement_month")
        if statement_year and statement_month:
            row_year, row_month = _previous_month(
                int(statement_year),
                int(statement_month),
            )

    subcategory = None
    if category == BILLS_CATEGORY:
        subcategory = resolve_expense_subcategory(
            category,
            vendor,
            vendor_rules or {},
        )

    return ImportExpenseRow(
        row_key=external_id,
        external_id=external_id,
        year=row_year,
        month=row_month,
        category=category,
        vendor=vendor,
        payment_account=payment_account,
        amount=amount,
        transaction_date=tx_date,
        already_exists=False,
        selected=True,
        is_reversal=is_reversal,
        subcategory=subcategory,
    )


def _normalize_deposit_transaction(
    tx: dict[str, Any],
    account_lookup: dict[str, dict[str, Any]],
) -> ImportIncomeRow | None:
    if str(tx.get("_source_kind") or "bank") != "bank":
        return None

    external_id = str(tx.get("transactionId") or tx.get("id") or "")
    if not external_id:
        return None

    if str(tx.get("creditDebitType", "")).upper() != "CREDITO":
        return None

    tx_type = str(tx.get("type") or "").upper()
    if tx_type in INVESTMENT_TRANSACTION_TYPES:
        return None

    amount_raw = _transaction_amount(tx)
    if amount_raw is None or amount_raw <= 0:
        return None

    tx_date = _parse_date(tx.get("transactionDateTime") or tx.get("transactionDate"))
    if tx_date is None:
        return None

    source_account = tx.get("_source_account")
    if isinstance(source_account, dict):
        account = source_account
    else:
        account_id = str(tx.get("accountId") or tx.get("account_id") or "")
        account = account_lookup.get(account_id, {})

    description = _transaction_vendor(tx)
    payment_account = map_payment_account(account, source_kind="bank")
    if payment_account not in PAYMENT_ACCOUNTS:
        payment_account = "Nuconta"

    return ImportIncomeRow(
        row_key=external_id,
        external_id=external_id,
        year=tx_date.year,
        month=tx_date.month,
        description=description,
        amount=abs(amount_raw),
        transaction_date=tx_date,
        payment_account=payment_account,
        already_exists=False,
        selected=True,
    )


def _normalize_transaction(
    tx: dict[str, Any],
    account_lookup: dict[str, dict[str, Any]],
) -> ImportExpenseRow | None:
    source_kind = str(tx.get("_source_kind") or "bank")
    return _normalize_expense_transaction(tx, account_lookup, source_kind=source_kind)


def _normalize_investment(
    item: dict[str, Any],
    slug_by_name: dict[str, str],
) -> ImportInvestmentRow | None:
    if is_exchange_traded_investment(item):
        return None

    external_id = str(item.get("id") or item.get("investmentId") or "")
    if not external_id:
        return None

    balance = _parse_decimal(
        item.get("balance") or item.get("currentValue") or item.get("amount")
    )
    if balance is None or balance < 0:
        return None

    slug = map_asset_type_slug(item)
    if slug not in slug_by_name:
        slug = "bonds"

    institution = str(item.get("institution") or item.get("issuer") or "Unknown").strip()
    name = str(item.get("name") or item.get("productName") or "Investment").strip()

    return ImportInvestmentRow(
        row_key=external_id,
        external_id=external_id,
        institution=institution,
        name=name,
        asset_type_slug=slug,
        current_value=balance,
        already_exists=False,
        selected=True,
        is_update=False,
    )


def _fetch_live_transactions(
    access_token: str,
    *,
    year: int,
    month: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    start, end = _month_bounds(year, month)
    return fetch_all_transactions(
        access_token,
        start_date=start,
        end_date=end,
        year=year,
        month=month,
    )


def _load_transaction_bundle(
    access_token: str | None,
    *,
    year: int,
    month: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    if use_fixture_mode() or access_token is None:
        fixture = _load_fixture("cumbuca_transactions.json")
        return (
            fixture.get("accounts", []),
            fixture.get("credit_cards", []),
            fixture.get("transactions", []),
            [],
        )

    start, end = _month_bounds(year, month)
    return _fetch_live_transactions(access_token, year=year, month=month)


def _account_lookup(
    accounts: list[dict[str, Any]],
    credit_cards: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    lookup = {
        str(account.get("accountId") or account.get("id") or ""): account
        for account in accounts
    }
    for card in credit_cards:
        card_id = str(
            card.get("creditCardAccountId") or card.get("credit_card_account_id") or ""
        )
        if card_id:
            lookup[card_id] = card
    return lookup


def build_credit_card_expense_import_rows(
    session: Session,
    user: User,
    *,
    year: int,
    month: int,
    access_token: str | None = None,
) -> tuple[list[ImportExpenseRow], list[str]]:
    accounts, credit_cards, transactions, warnings = _load_transaction_bundle(
        access_token,
        year=year,
        month=month,
    )
    account_lookup = _account_lookup(accounts, credit_cards)
    existing_ids = _existing_expense_ids(session, user.id)
    vendor_rules = load_vendor_rule_map(session, user.id)
    rows: list[ImportExpenseRow] = []

    for tx in transactions:
        row = _normalize_expense_transaction(
            tx,
            account_lookup,
            source_kind="credit_card",
            vendor_rules=vendor_rules,
        )
        if row is None:
            continue
        if not _row_matches_import(row, tx, year, month):
            continue
        row.already_exists = row.external_id in existing_ids
        row.selected = not row.already_exists
        rows.append(row)

    rows.sort(key=lambda item: (item.transaction_date, item.vendor))
    return rows, warnings


def build_account_expense_import_rows(
    session: Session,
    user: User,
    *,
    year: int,
    month: int,
    access_token: str | None = None,
) -> tuple[list[ImportExpenseRow], list[str]]:
    accounts, credit_cards, transactions, warnings = _load_transaction_bundle(
        access_token,
        year=year,
        month=month,
    )
    account_lookup = _account_lookup(accounts, credit_cards)
    existing_ids = _existing_expense_ids(session, user.id)
    vendor_rules = load_vendor_rule_map(session, user.id)
    rows: list[ImportExpenseRow] = []

    for tx in transactions:
        row = _normalize_expense_transaction(
            tx,
            account_lookup,
            source_kind="bank",
            vendor_rules=vendor_rules,
        )
        if row is None:
            continue
        if not _row_matches_import(row, tx, year, month):
            continue
        row.already_exists = row.external_id in existing_ids
        row.selected = not row.already_exists
        rows.append(row)

    rows.sort(key=lambda item: (item.transaction_date, item.vendor))
    return rows, warnings


def build_account_deposit_import_rows(
    session: Session,
    user: User,
    *,
    year: int,
    month: int,
    access_token: str | None = None,
) -> tuple[list[ImportIncomeRow], list[str]]:
    accounts, credit_cards, transactions, warnings = _load_transaction_bundle(
        access_token,
        year=year,
        month=month,
    )
    account_lookup = _account_lookup(accounts, credit_cards)
    existing_ids = _existing_income_ids(session, user.id)
    rows: list[ImportIncomeRow] = []

    for tx in transactions:
        row = _normalize_deposit_transaction(tx, account_lookup)
        if row is None:
            continue
        if row.year != year or row.month != month:
            continue
        row.already_exists = row.external_id in existing_ids
        row.selected = not row.already_exists
        rows.append(row)

    rows.sort(key=lambda item: (item.transaction_date, item.description))
    return rows, warnings


def build_expense_import_rows(
    session: Session,
    user: User,
    *,
    year: int,
    month: int,
    access_token: str | None = None,
) -> tuple[list[ImportExpenseRow], list[str]]:
    cc_rows, cc_warnings = build_credit_card_expense_import_rows(
        session,
        user,
        year=year,
        month=month,
        access_token=access_token,
    )
    bank_rows, bank_warnings = build_account_expense_import_rows(
        session,
        user,
        year=year,
        month=month,
        access_token=access_token,
    )
    rows = cc_rows + bank_rows
    rows.sort(key=lambda item: (item.transaction_date, item.vendor))
    return rows, cc_warnings + bank_warnings


def build_investment_import_rows(
    session: Session,
    *,
    access_token: str | None = None,
) -> list[ImportInvestmentRow]:
    asset_types = get_investable_asset_types(session)
    slug_by_name = {asset_type.slug: asset_type.slug for asset_type in asset_types}
    name_to_slug = {asset_type.name.lower(): asset_type.slug for asset_type in asset_types}
    slug_by_name.update(name_to_slug)

    if use_fixture_mode() or access_token is None:
        investments = _load_fixture("cumbuca_investments.json").get("investments", [])
    else:
        investments = fetch_investments(access_token)

    existing = _existing_investment_map(session)
    rows: list[ImportInvestmentRow] = []

    for item in investments:
        row = _normalize_investment(item, slug_by_name)
        if row is None:
            continue
        if row.external_id in existing:
            row.already_exists = True
            row.is_update = True
            row.selected = True
        rows.append(row)

    rows.sort(key=lambda item: (item.institution, item.name))
    return rows


def stash_finance_import(rows: list[ImportExpenseRow]) -> str:
    token = str(uuid4())
    _finance_stash[token] = StashedFinanceImport(rows=rows)
    return token


def pop_stashed_finance_import(token: str) -> list[ImportExpenseRow] | None:
    payload = _finance_stash.pop(token, None)
    if payload is None:
        return None
    return payload.rows


def stash_income_import(rows: list[ImportIncomeRow]) -> str:
    token = str(uuid4())
    _income_stash[token] = StashedIncomeImport(rows=rows)
    return token


def pop_stashed_income_import(token: str) -> list[ImportIncomeRow] | None:
    payload = _income_stash.pop(token, None)
    if payload is None:
        return None
    return payload.rows


def stash_investment_import(rows: list[ImportInvestmentRow]) -> str:
    token = str(uuid4())
    _investment_stash[token] = StashedInvestmentImport(rows=rows)
    return token


def pop_stashed_investment_import(token: str) -> list[ImportInvestmentRow] | None:
    payload = _investment_stash.pop(token, None)
    if payload is None:
        return None
    return payload.rows


def import_selected_expenses(
    session: Session,
    user_id: UUID,
    rows: list[ImportExpenseRow],
    selected_keys: set[str],
    category_overrides: dict[str, str] | None = None,
    subcategory_overrides: dict[str, str | None] | None = None,
) -> int:
    overrides = category_overrides or {}
    subcategory_overrides = subcategory_overrides or {}
    vendor_rules = load_vendor_rule_map(session, user_id)
    created = 0
    for row in rows:
        if row.row_key not in selected_keys or row.already_exists:
            continue
        category = overrides.get(row.row_key, row.category)
        if category not in EXPENSE_CATEGORIES:
            category = "Outros"

        if row.row_key in subcategory_overrides:
            explicit = subcategory_overrides[row.row_key] or ""
            subcategory = (
                resolve_expense_subcategory(
                    category,
                    row.vendor,
                    vendor_rules,
                    explicit_subcategory=explicit,
                )
                if category == BILLS_CATEGORY
                else None
            )
        elif category == BILLS_CATEGORY:
            subcategory = row.subcategory or resolve_expense_subcategory(
                category,
                row.vendor,
                vendor_rules,
            )
        else:
            subcategory = None

        session.add(
            FinanceExpenseEntry(
                user_id=user_id,
                year=row.year,
                month=row.month,
                transaction_date=row.transaction_date,
                category=category,
                vendor=row.vendor,
                payment_account=row.payment_account,
                amount=row.amount,
                subcategory=subcategory,
                source=OPEN_FINANCE_SOURCE,
                external_id=row.external_id,
            )
        )
        save_vendor_category(
            session, user_id, row.vendor, category, subcategory=subcategory
        )
        created += 1
    if created:
        session.commit()
    return created


def import_selected_income(
    session: Session,
    user_id: UUID,
    rows: list[ImportIncomeRow],
    selected_keys: set[str],
) -> int:
    created = 0
    for row in rows:
        if row.row_key not in selected_keys or row.already_exists:
            continue
        session.add(
            FinanceIncomeEntry(
                user_id=user_id,
                year=row.year,
                month=row.month,
                category="Outros",
                description=row.description,
                amount=row.amount,
                source=OPEN_FINANCE_SOURCE,
                external_id=row.external_id,
            )
        )
        created += 1
    if created:
        session.commit()
    return created


def import_selected_investments(
    session: Session,
    rows: list[ImportInvestmentRow],
    selected_keys: set[str],
) -> tuple[int, int]:
    asset_types = get_investable_asset_types(session)
    slug_to_id = {asset_type.slug: asset_type.id for asset_type in asset_types}
    name_to_id = {asset_type.name.lower(): asset_type.id for asset_type in asset_types}

    existing = _existing_investment_map(session)
    created = 0
    updated = 0

    for row in rows:
        if row.row_key not in selected_keys:
            continue
        asset_type_id = slug_to_id.get(row.asset_type_slug) or name_to_id.get(
            row.asset_type_slug
        )
        if asset_type_id is None:
            asset_type_id = slug_to_id.get("bonds") or next(iter(slug_to_id.values()))

        current = existing.get(row.external_id)
        if current:
            current.institution = row.institution
            current.name = row.name
            current.current_value = row.current_value
            current.asset_type_id = asset_type_id
            current.source = OPEN_FINANCE_SOURCE
            current.updated_at = datetime.utcnow()
            session.add(current)
            updated += 1
            continue

        investment = Investment(
            asset_type_id=asset_type_id,
            institution=row.institution,
            name=row.name,
            current_value=row.current_value,
            source=OPEN_FINANCE_SOURCE,
            external_id=row.external_id,
        )
        session.add(investment)
        created += 1

    if created or updated:
        session.commit()

    return created, updated


def get_access_token_for_user(session: Session, user: User) -> str:
    return refresh_access_token(session, user)


def fetch_open_finance_error(exc: Exception) -> str:
    if isinstance(exc, CumbucaMcpError):
        return str(exc)
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, ExceptionGroup):
        for sub in exc.exceptions:
            message = fetch_open_finance_error(sub)
            if message != "Could not fetch Open Finance data.":
                return message
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause and cause is not exc:
        return fetch_open_finance_error(cause)
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 401:
            return "Open Finance authentication failed. Reconnect your bank."
        return f"Open Finance request failed ({exc.response.status_code})."
    return "Could not fetch Open Finance data."
