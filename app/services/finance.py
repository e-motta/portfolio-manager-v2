import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from collections.abc import Callable
from uuid import UUID

from sqlmodel import Session, select
from sqlalchemy import nulls_last

from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceInvestmentEntry,
    FinanceTransferEntry,
    FinanceVendorCategory,
)

MONTH_LABELS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

BILLS_CATEGORY = "Bills"
BILLS_PAYMENT_ACCOUNT = "Nuconta"
DAY_TO_DAY_ALWAYS_PAID_ACCOUNTS = frozenset({BILLS_PAYMENT_ACCOUNT})
BILLS_SUBCATEGORY_ALUGUEL = "Aluguel (/2+114)"
BILLS_SUBCATEGORY_OUTRAS_CONTAS = "Outras contas (/2)"
BILLS_SUBCATEGORIES = (
    BILLS_SUBCATEGORY_ALUGUEL,
    BILLS_SUBCATEGORY_OUTRAS_CONTAS,
)

EXPENSE_SUBCATEGORY_SLUGS: dict[str, str] = {
    BILLS_SUBCATEGORY_ALUGUEL: "bills-aluguel",
    BILLS_SUBCATEGORY_OUTRAS_CONTAS: "bills-outras",
}

_UNSET = object()

EXPENSE_CATEGORIES = (
    BILLS_CATEGORY,
    "Alimentação fora",
    "Supermercado",
    "Suplementos",
    "Corrida",
    "Academia e treino",
    "Assinaturas digitais",
    "Telecom",
    "Seguros",
    "Contabilidade / PJ",
    "Saúde",
    "Casa",
    "Transporte",
    "Compras online",
    "Bar e lazer",
    "Presentes",
    "Profissional",
    "Outros",
)

EXPENSE_CATEGORY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Bills", (BILLS_CATEGORY,)),
    ("Alimentação", ("Alimentação fora", "Supermercado")),
    ("Esporte", ("Suplementos", "Corrida", "Academia e treino")),
    ("Assinaturas", ("Assinaturas digitais", "Telecom", "Seguros", "Contabilidade / PJ")),
    (
        "Vida",
        (
            "Saúde",
            "Casa",
            "Transporte",
            "Compras online",
            "Bar e lazer",
            "Presentes",
            "Profissional",
        ),
    ),
    ("Outros", ("Outros",)),
)

EXPENSE_CATEGORY_SLUGS: dict[str, str] = {
    BILLS_CATEGORY: "bills",
    "Alimentação fora": "food-out",
    "Supermercado": "grocery",
    "Suplementos": "supplements",
    "Corrida": "running",
    "Academia e treino": "gym",
    "Assinaturas digitais": "subscriptions",
    "Telecom": "telecom",
    "Seguros": "insurance",
    "Contabilidade / PJ": "accounting",
    "Saúde": "health",
    "Casa": "home",
    "Transporte": "transport",
    "Compras online": "online",
    "Bar e lazer": "leisure",
    "Presentes": "gifts",
    "Profissional": "professional",
    "Outros": "other",
}

LEGACY_EXPENSE_CATEGORY_MIGRATION = {
    "Restaurante + entrega": "Alimentação fora",
    "Lanche/janta": "Supermercado",
    "Lanche e café": "Supermercado",
    "Supermercado + online": "Supermercado",
    "Bar + bebidas": "Bar e lazer",
    "Uber": "Transporte",
    "Fixos": "Assinaturas digitais",
}

PAYMENT_ACCOUNTS = (
    "Nubank",
    "Nuconta",
    "XP Crédito",
    "BB Crédito",
    "BB Débito",
    "Wise",
    "Dinheiro",
    "Manual",
)

TRANSFER_ACCOUNTS = tuple(account for account in PAYMENT_ACCOUNTS if account != "Manual")

FINANCE_SOURCE_LABELS = {
    "manual": "Manual",
    "open_finance": "Open Finance",
}


def format_finance_source(source: str | None) -> str:
    if not source:
        return FINANCE_SOURCE_LABELS["manual"]
    return FINANCE_SOURCE_LABELS.get(source, source.replace("_", " ").title())


def expense_category_slug(category: str) -> str:
    return EXPENSE_CATEGORY_SLUGS.get(category, "other")


def expense_subcategory_slug(subcategory: str | None) -> str:
    if not subcategory:
        return "none"
    return EXPENSE_SUBCATEGORY_SLUGS.get(subcategory, "none")

MAX_EXPENSE_INSTALLMENTS = 48

INCOME_CATEGORIES = ("PJ", "Outros")

INVESTMENT_BROKERS = (
    ("xp", "XP"),
    ("ib", "IB"),
    ("nubank", "Nubank"),
    ("mb", "MB"),
)

INVESTMENT_TARGET_RATE = Decimal("0.30")

MIGRATED_SUMMARY_SOURCE = "migrated_summary"

SUMMARY_BILL_LINE_LABELS = {
    "aluguel": "Aluguel",
    "internet": "Internet",
    "luz": "Luz",
    "gas": "Gás",
}

SUMMARY_CC_LINE_ACCOUNTS = {
    "cc_ourocard": "BB Crédito",
    "cc_nubank": "Nubank",
    "cc_xp": "XP Crédito",
    "regular_outros": "Manual",
}

SUMMARY_INVESTMENT_BROKERS = {
    "inv_xp": "xp",
    "inv_ib": "ib",
    "inv_nubank": "nubank",
    "inv_mb": "mb",
}

SUMMARY_INCOME_LINE_CATEGORIES = {
    "pj": "PJ",
    "pro_labore": "PJ",
    "lucro": "PJ",
}


_INSTALLMENT_VENDOR_SUFFIX = re.compile(
    r"\s*(?:\(\s*)?\d+\s*/\s*\d+\s*(?:\))?\s*$"
)


def normalize_vendor_key(vendor: str) -> str:
    name = vendor.strip()
    if "|" in name:
        name = name.split("|", 1)[1].strip()
    name = _INSTALLMENT_VENDOR_SUFFIX.sub("", name).strip()
    normalized = name.lower()
    return normalized or "unknown"


def suggest_expense_category(vendor: str, current_category: str = "") -> str:
    vendor_key = normalize_vendor_key(vendor)

    if any(
        keyword in vendor_key
        for keyword in (
            "example accessory",
            "pulseiras relógio",
            "pulseiras relogio",
            "capa celular",
        )
    ):
        return "Compras online"
    if vendor_key in {"amazon", "mercado livre"}:
        return "Compras online"
    if any(
        keyword in vendor_key
        for keyword in (
            "puravida",
            "growth",
            "hydrolite",
            "gel dobro",
        )
    ):
        return "Suplementos"
    if vendor_key == "eon" or vendor_key.startswith("corrida") or any(
        keyword in vendor_key
        for keyword in ("safety run", "foto corrida", "netshoes example", "asics superblast")
    ):
        return "Corrida"
    if any(
        keyword in vendor_key
        for keyword in (
            "regata tf",
            "bermuda+boné",
            "bermuda+bone",
            "meias netshoes",
            "luva shopee",
            "garrafa shopee",
            "elásticos exercício",
            "elasticos exercicio",
        )
    ):
        return "Corrida"
    if any(keyword in vendor_key for keyword in ("dentista", "fisio", "cabelo")):
        return "Saúde"
    if any(keyword in vendor_key for keyword in ("anuidade oab", "udemy", "curso ")):
        return "Profissional"
    if vendor_key == "coco":
        return "Bar e lazer"
    if "presente" in vendor_key:
        return "Presentes"
    if any(
        keyword in vendor_key
        for keyword in (
            "panela",
            "mop shopee",
            "pegador panela",
            "rodo pia",
            "suporte ",
            "lâmpada shopee",
            "lampada shopee",
            "isolamento porta",
            "funil",
        )
    ):
        return "Casa"
    if vendor_key == "rd":
        return "Assinaturas digitais"
    if vendor_key == "gogood":
        return "Academia e treino"
    if any(keyword in vendor_key for keyword in ("spotify", "youtube", "cursor")):
        return "Assinaturas digitais"
    if "nucel" in vendor_key:
        return "Telecom"
    if "seguro" in vendor_key:
        return "Seguros"
    if "contabilizei" in vendor_key:
        return "Contabilidade / PJ"
    if any(
        keyword in vendor_key
        for keyword in ("angeloni", "hiperbom", "nativa", "imperatriz", "baggio")
    ):
        return "Supermercado"
    if vendor_key == "example cafe":
        return "Alimentação fora"
    if "uber" in vendor_key:
        return "Transporte"
    if "outback" in vendor_key or "restaurante" in vendor_key:
        return "Alimentação fora"

    migrated = LEGACY_EXPENSE_CATEGORY_MIGRATION.get(current_category, current_category)
    if migrated in EXPENSE_CATEGORIES:
        return migrated
    return "Outros"


def migrate_expense_categories(session: Session) -> int:
    updated = 0

    for entry in session.exec(select(FinanceExpenseEntry)).all():
        new_category = suggest_expense_category(entry.vendor, entry.category)
        if new_category != entry.category:
            entry.category = new_category
            session.add(entry)
            updated += 1

    for rule in session.exec(select(FinanceVendorCategory)).all():
        new_category = suggest_expense_category(rule.vendor_key, rule.category)
        if new_category != rule.category:
            rule.category = new_category
            session.add(rule)
            updated += 1

    if updated:
        session.commit()
    return updated


def load_vendor_category_map(session: Session, user_id: UUID) -> dict[str, str]:
    rows = session.exec(
        select(FinanceVendorCategory).where(FinanceVendorCategory.user_id == user_id)
    ).all()
    return {row.vendor_key: row.category for row in rows}


def load_vendor_rule_map(
    session: Session, user_id: UUID
) -> dict[str, tuple[str, str | None]]:
    rows = session.exec(
        select(FinanceVendorCategory).where(FinanceVendorCategory.user_id == user_id)
    ).all()
    return {row.vendor_key: (row.category, row.subcategory) for row in rows}


def normalize_expense_subcategory(category: str, subcategory: str | None) -> str | None:
    if not subcategory or not subcategory.strip():
        return None
    cleaned = subcategory.strip()
    if category != BILLS_CATEGORY:
        if cleaned:
            raise ValueError("Subcategory is only allowed for Bills.")
        return None
    if cleaned not in BILLS_SUBCATEGORIES:
        raise ValueError("Invalid subcategory.")
    return cleaned


def resolve_expense_subcategory(
    category: str,
    vendor: str,
    vendor_rules: dict[str, tuple[str, str | None]],
    *,
    explicit_subcategory: str | None | object = _UNSET,
) -> str | None:
    if explicit_subcategory is not _UNSET:
        if not explicit_subcategory or not str(explicit_subcategory).strip():
            return None
        return normalize_expense_subcategory(category, str(explicit_subcategory))
    if category != BILLS_CATEGORY:
        return None
    vendor_key = normalize_vendor_key(vendor)
    rule = vendor_rules.get(vendor_key)
    if rule is None:
        return None
    saved_subcategory = rule[1]
    if saved_subcategory in BILLS_SUBCATEGORIES:
        return saved_subcategory
    return None


def effective_expense_amount_for(
    amount: Decimal,
    subcategory: str | None,
) -> Decimal:
    if not subcategory:
        return amount

    magnitude = abs(amount)
    if subcategory == BILLS_SUBCATEGORY_ALUGUEL:
        adjusted = magnitude / Decimal("2") + Decimal("114")
    elif subcategory == BILLS_SUBCATEGORY_OUTRAS_CONTAS:
        adjusted = magnitude / Decimal("2")
    else:
        return amount

    adjusted = adjusted.quantize(Decimal("0.01"))
    if amount > 0:
        return adjusted
    if amount < 0:
        return -adjusted
    return Decimal("0")


def effective_expense_amount(
    entry: FinanceExpenseEntry,
    *,
    amount: Decimal | None = None,
    subcategory: str | None = None,
) -> Decimal:
    raw_amount = entry.amount if amount is None else amount
    effective_subcategory = entry.subcategory if subcategory is None else subcategory
    return effective_expense_amount_for(raw_amount, effective_subcategory)


def save_vendor_category(
    session: Session,
    user_id: UUID,
    vendor: str,
    category: str,
    *,
    subcategory: str | None = None,
) -> None:
    if category not in EXPENSE_CATEGORIES:
        return
    vendor_key = normalize_vendor_key(vendor)
    if not vendor_key or vendor_key == "unknown":
        return

    normalized_subcategory: str | None
    try:
        normalized_subcategory = normalize_expense_subcategory(category, subcategory)
    except ValueError:
        normalized_subcategory = None

    existing = session.exec(
        select(FinanceVendorCategory)
        .where(FinanceVendorCategory.user_id == user_id)
        .where(FinanceVendorCategory.vendor_key == vendor_key)
    ).first()
    if existing is None:
        session.add(
            FinanceVendorCategory(
                user_id=user_id,
                vendor_key=vendor_key,
                category=category,
                subcategory=normalized_subcategory,
            )
        )
        return

    changed = False
    if existing.category != category:
        existing.category = category
        changed = True
    if existing.subcategory != normalized_subcategory:
        existing.subcategory = normalized_subcategory
        changed = True
    if changed:
        existing.updated_at = datetime.utcnow()
        session.add(existing)


def build_monthly_chart(
    month_values: dict[int, Decimal],
    *,
    year: int,
    selected_month: int | None,
    link_base: str,
    variant: str,
    aria_label: str,
) -> dict:
    highlight_month = resolve_month(selected_month, year)
    return {
        "ariaLabel": aria_label,
        "variant": variant,
        "year": year,
        "selectedMonth": highlight_month,
        "linkBase": link_base,
        "points": [
            {
                "month": month,
                "label": MONTH_LABELS[month - 1][:3],
                "value": float(month_values.get(month, Decimal("0"))),
            }
            for month in range(1, 13)
        ],
    }


def build_summary_monthly_chart(
    income_by_month: dict[int, Decimal],
    expense_by_month: dict[int, Decimal],
    balance_by_month: dict[int, Decimal],
    *,
    year: int,
    selected_month: int | None,
    link_base: str,
    aria_label: str,
) -> dict:
    highlight_month = resolve_month(selected_month, year)
    return {
        "ariaLabel": aria_label,
        "variant": "summary",
        "year": year,
        "selectedMonth": highlight_month,
        "linkBase": link_base,
        "points": [
            {
                "month": month,
                "label": MONTH_LABELS[month - 1][:3],
                "income": float(income_by_month.get(month, Decimal("0"))),
                "expense": float(expense_by_month.get(month, Decimal("0"))),
                "balance": float(balance_by_month.get(month, Decimal("0"))),
            }
            for month in range(1, 13)
        ],
    }


def validate_income_category(category: str) -> str:
    if category not in INCOME_CATEGORIES:
        raise ValueError(f"Invalid income category: {category}")
    return category


def validate_investment_broker(broker: str) -> str:
    allowed = {key for key, _ in INVESTMENT_BROKERS}
    if broker not in allowed:
        raise ValueError(f"Invalid broker: {broker}")
    return broker


def validate_transfer_account(account: str) -> str:
    if account not in TRANSFER_ACCOUNTS:
        raise ValueError(f"Invalid account: {account}")
    return account


def validate_transfer_accounts(from_account: str, to_account: str) -> tuple[str, str]:
    parsed_from = validate_transfer_account(from_account)
    parsed_to = validate_transfer_account(to_account)
    if parsed_from == parsed_to:
        raise ValueError("From and to accounts must be different.")
    return parsed_from, parsed_to


def investment_broker_label(broker: str) -> str:
    for key, label in INVESTMENT_BROKERS:
        if key == broker:
            return label
    return broker


def _summary_external_id(line_key: str, year: int, month: int) -> str:
    return f"summary:{line_key}:{year}:{month}"


class FinanceSummaryAmountLegacy:
    """Runtime-only row shape for migration before table drop."""

    __slots__ = ("user_id", "year", "month", "line_key", "amount")

    def __init__(
        self,
        user_id: UUID,
        year: int,
        month: int,
        line_key: str,
        amount: Decimal,
    ) -> None:
        self.user_id = user_id
        self.year = year
        self.month = month
        self.line_key = line_key
        self.amount = amount


def _load_legacy_summary_rows(session: Session) -> list[FinanceSummaryAmountLegacy]:
    from sqlalchemy import inspect, text

    bind = session.get_bind()
    inspector = inspect(bind)
    if "finance_summary_amounts" not in inspector.get_table_names():
        return []

    result = bind.execute(
        text(
            "SELECT user_id, year, month, line_key, amount "
            "FROM finance_summary_amounts"
        )
    )
    return [
        FinanceSummaryAmountLegacy(
            user_id=UUID(str(row.user_id)),
            year=row.year,
            month=row.month,
            line_key=row.line_key,
            amount=Decimal(str(row.amount)),
        )
        for row in result
    ]


def migrate_finance_summary_to_entries(session: Session) -> int:
    rows = _load_legacy_summary_rows(session)
    if not rows:
        return 0

    inserted = 0
    for row in rows:
        external_id = _summary_external_id(row.line_key, row.year, row.month)
        if row.line_key in SUMMARY_INCOME_LINE_CATEGORIES:
            category = SUMMARY_INCOME_LINE_CATEGORIES[row.line_key]
            existing = session.exec(
                select(FinanceIncomeEntry)
                .where(FinanceIncomeEntry.user_id == row.user_id)
                .where(FinanceIncomeEntry.external_id == external_id)
            ).first()
            if existing:
                continue
            amount = abs(row.amount)
            if amount == 0:
                continue
            session.add(
                FinanceIncomeEntry(
                    user_id=row.user_id,
                    year=row.year,
                    month=row.month,
                    category=category,
                    description=category,
                    amount=amount,
                    source=MIGRATED_SUMMARY_SOURCE,
                    external_id=external_id,
                )
            )
            inserted += 1
        elif row.line_key in SUMMARY_BILL_LINE_LABELS:
            existing = session.exec(
                select(FinanceExpenseEntry)
                .where(FinanceExpenseEntry.user_id == row.user_id)
                .where(FinanceExpenseEntry.external_id == external_id)
            ).first()
            if existing:
                continue
            amount = row.amount
            if amount == 0:
                continue
            if amount > 0:
                amount = -abs(amount)
            session.add(
                FinanceExpenseEntry(
                    user_id=row.user_id,
                    year=row.year,
                    month=row.month,
                    category=BILLS_CATEGORY,
                    vendor=SUMMARY_BILL_LINE_LABELS[row.line_key],
                    payment_account=BILLS_PAYMENT_ACCOUNT,
                    amount=amount,
                    source=MIGRATED_SUMMARY_SOURCE,
                    external_id=external_id,
                )
            )
            inserted += 1
        elif row.line_key in SUMMARY_CC_LINE_ACCOUNTS:
            existing = session.exec(
                select(FinanceExpenseEntry)
                .where(FinanceExpenseEntry.user_id == row.user_id)
                .where(FinanceExpenseEntry.external_id == external_id)
            ).first()
            if existing:
                continue
            amount = row.amount
            if amount == 0:
                continue
            if amount > 0:
                amount = -abs(amount)
            session.add(
                FinanceExpenseEntry(
                    user_id=row.user_id,
                    year=row.year,
                    month=row.month,
                    category="Outros",
                    vendor=row.line_key.replace("_", " ").title(),
                    payment_account=SUMMARY_CC_LINE_ACCOUNTS[row.line_key],
                    amount=amount,
                    source=MIGRATED_SUMMARY_SOURCE,
                    external_id=external_id,
                )
            )
            inserted += 1
        elif row.line_key in SUMMARY_INVESTMENT_BROKERS:
            broker = SUMMARY_INVESTMENT_BROKERS[row.line_key]
            existing = session.exec(
                select(FinanceInvestmentEntry)
                .where(FinanceInvestmentEntry.user_id == row.user_id)
                .where(FinanceInvestmentEntry.year == row.year)
                .where(FinanceInvestmentEntry.month == row.month)
                .where(FinanceInvestmentEntry.broker == broker)
            ).first()
            amount = abs(row.amount)
            if amount == 0:
                continue
            if existing:
                existing.amount = amount
                session.add(existing)
            else:
                session.add(
                    FinanceInvestmentEntry(
                        user_id=row.user_id,
                        year=row.year,
                        month=row.month,
                        broker=broker,
                        amount=amount,
                    )
                )
            inserted += 1

    session.commit()
    return inserted


@dataclass
class MonthAmounts:
    months: dict[int, Decimal] = field(default_factory=lambda: {m: Decimal("0") for m in range(1, 13)})

    def get(self, month: int) -> Decimal:
        return self.months.get(month, Decimal("0"))

    def set(self, month: int, amount: Decimal) -> None:
        self.months[month] = amount

    def total(self) -> Decimal:
        return sum(self.months.values(), start=Decimal("0"))

    def average(self, active_months: int) -> Decimal:
        if active_months <= 0:
            return Decimal("0")
        return self.total() / Decimal(active_months)


def resolve_year(year: int | None) -> int:
    return year or date.today().year


def resolve_month(month: int | None, year: int) -> int:
    if month is not None and 1 <= month <= 12:
        return month
    if year == date.today().year:
        return date.today().month
    return 1


def month_has_activity(amount: Decimal) -> bool:
    return amount != 0


def _empty_month_map() -> dict[int, Decimal]:
    return {month: Decimal("0") for month in range(1, 13)}


def _load_income_entries(
    session: Session, user_id: UUID, year: int
) -> list[FinanceIncomeEntry]:
    return list(
        session.exec(
            select(FinanceIncomeEntry)
            .where(FinanceIncomeEntry.user_id == user_id)
            .where(FinanceIncomeEntry.year == year)
            .order_by(FinanceIncomeEntry.month, FinanceIncomeEntry.description)
        ).all()
    )


def _load_expense_entries(
    session: Session, user_id: UUID, year: int
) -> list[FinanceExpenseEntry]:
    return list(
        session.exec(
            select(FinanceExpenseEntry)
            .where(FinanceExpenseEntry.user_id == user_id)
            .where(FinanceExpenseEntry.year == year)
            .order_by(
                FinanceExpenseEntry.category,
                FinanceExpenseEntry.month,
                nulls_last(FinanceExpenseEntry.transaction_date.desc()),
                FinanceExpenseEntry.vendor,
            )
        ).all()
    )


def is_expense_reversal(entry: FinanceExpenseEntry) -> bool:
    return entry.amount > 0


def linkable_expenses_for_reversal(
    reversal: FinanceExpenseEntry,
    entries: list[FinanceExpenseEntry],
) -> list[FinanceExpenseEntry]:
    if not is_expense_reversal(reversal):
        return []

    candidates = [
        entry
        for entry in entries
        if entry.id != reversal.id
        and entry.amount < 0
        and entry.month == reversal.month
    ]
    candidates.sort(
        key=lambda entry: (
            entry.payment_account != reversal.payment_account,
            entry.vendor.lower(),
        )
    )
    return candidates


def link_expense_reversal(
    session: Session,
    *,
    user_id: UUID,
    reversal_id: UUID,
    target_id: UUID,
) -> FinanceExpenseEntry:
    reversal = session.get(FinanceExpenseEntry, reversal_id)
    target = session.get(FinanceExpenseEntry, target_id)
    if (
        not reversal
        or not target
        or reversal.user_id != user_id
        or target.user_id != user_id
    ):
        raise ValueError("Expense not found.")
    if not is_expense_reversal(reversal):
        raise ValueError("Only reversal entries can be linked.")
    if target.amount >= 0:
        raise ValueError("Target must be a charge.")
    if reversal.year != target.year or reversal.month != target.month:
        raise ValueError("Reversal and charge must be in the same month.")

    target.amount += reversal.amount
    target.updated_at = datetime.utcnow()
    session.delete(reversal)
    session.add(target)
    return target


def _load_investment_entries(
    session: Session, user_id: UUID, year: int
) -> list[FinanceInvestmentEntry]:
    return list(
        session.exec(
            select(FinanceInvestmentEntry)
            .where(FinanceInvestmentEntry.user_id == user_id)
            .where(FinanceInvestmentEntry.year == year)
            .order_by(
                FinanceInvestmentEntry.month,
                FinanceInvestmentEntry.broker,
            )
        ).all()
    )


def _load_transfer_entries(
    session: Session, user_id: UUID, year: int
) -> list[FinanceTransferEntry]:
    return list(
        session.exec(
            select(FinanceTransferEntry)
            .where(FinanceTransferEntry.user_id == user_id)
            .where(FinanceTransferEntry.year == year)
            .order_by(
                FinanceTransferEntry.month,
                FinanceTransferEntry.transaction_date,
                FinanceTransferEntry.from_account,
                FinanceTransferEntry.to_account,
            )
        ).all()
    )


def _sum_income_by_category(
    entries: list[FinanceIncomeEntry],
) -> dict[str, dict[int, Decimal]]:
    totals = {category: _empty_month_map() for category in INCOME_CATEGORIES}
    for entry in entries:
        category = entry.category if entry.category in INCOME_CATEGORIES else "Outros"
        totals[category][entry.month] += entry.amount
    return totals


def _sum_expenses_excluding_bills(
    entries: list[FinanceExpenseEntry],
) -> dict[str, dict[int, Decimal]]:
    totals = {account: _empty_month_map() for account in PAYMENT_ACCOUNTS}
    for entry in entries:
        if entry.category == BILLS_CATEGORY:
            continue
        account = entry.payment_account if entry.payment_account in totals else "Manual"
        totals.setdefault(account, _empty_month_map())
        totals[account][entry.month] += effective_expense_amount(entry)
    return totals


def _sum_bills_by_vendor(
    entries: list[FinanceExpenseEntry],
) -> dict[str, dict[int, Decimal]]:
    totals: dict[str, dict[int, Decimal]] = {}
    for entry in entries:
        if entry.category != BILLS_CATEGORY:
            continue
        vendor = entry.vendor or "Bills"
        totals.setdefault(vendor, _empty_month_map())
        totals[vendor][entry.month] += effective_expense_amount(entry)
    return totals


def _sum_bills_by_month(entries: list[FinanceExpenseEntry]) -> dict[int, Decimal]:
    totals = _empty_month_map()
    for entry in entries:
        if entry.category == BILLS_CATEGORY:
            totals[entry.month] += effective_expense_amount(entry)
    return totals


def _sum_day_to_day_by_month(entries: list[FinanceExpenseEntry]) -> dict[int, Decimal]:
    totals = _empty_month_map()
    for entry in entries:
        if entry.category != BILLS_CATEGORY:
            totals[entry.month] += effective_expense_amount(entry)
    return totals


def _active_month_count_from_entries(
    year: int,
    income_by_month: dict[int, Decimal],
    expense_by_month: dict[int, Decimal],
) -> int:
    active = set()
    for month in range(1, 13):
        if income_by_month[month] != 0 or expense_by_month[month] != 0:
            active.add(month)
    if year == date.today().year:
        active = {m for m in active if m <= date.today().month}
    return max(len(active), 1)


def _sum_by_month(
    entries: list[FinanceIncomeEntry] | list[FinanceExpenseEntry],
) -> dict[int, Decimal]:
    totals = _empty_month_map()
    for entry in entries:
        totals[entry.month] += entry.amount
    return totals


def _sum_expenses_by_month(entries: list[FinanceExpenseEntry]) -> dict[int, Decimal]:
    totals = _empty_month_map()
    for entry in entries:
        totals[entry.month] += effective_expense_amount(entry)
    return totals


def _card_lines_for_month(
    line_totals: dict[str, dict[int, Decimal]],
    month: int,
    *,
    ordered_keys: tuple[str, ...] | None = None,
    always_paid: bool = False,
    paid_for_line: Callable[[str, Decimal], bool] | None = None,
) -> list[dict[str, object]]:
    keys = ordered_keys or tuple(line_totals.keys())
    lines: list[dict[str, object]] = []
    for key in keys:
        total = line_totals.get(key, {}).get(month, Decimal("0"))
        if total != 0:
            line: dict[str, object] = {"label": key, "amount": total}
            if always_paid:
                line["paid"] = True
            elif paid_for_line is not None:
                line["paid"] = paid_for_line(key, total)
            lines.append(line)
    return lines


def _transfer_amounts_lookup(
    entries: list[FinanceTransferEntry],
) -> set[tuple[int, str, Decimal]]:
    return {
        (entry.month, entry.to_account, entry.amount)
        for entry in entries
    }


def _day_to_day_line_is_paid(
    month: int,
    account: str,
    amount: Decimal,
    transfer_lookup: set[tuple[int, str, Decimal]],
) -> bool:
    if account in DAY_TO_DAY_ALWAYS_PAID_ACCOUNTS:
        return True
    return (month, account, abs(amount)) in transfer_lookup


def build_income_context(
    session: Session, user_id: UUID, year: int, *, selected_month: int | None = None
) -> dict:
    entries = _load_income_entries(session, user_id, year)
    month_totals = _sum_by_month(entries)
    income_by_category = _sum_income_by_category(entries)
    category_month_totals = income_by_category
    category_year_totals = {
        category: sum(month_map.values(), start=Decimal("0"))
        for category, month_map in income_by_category.items()
    }
    entries_by_month: dict[int, list[FinanceIncomeEntry]] = {m: [] for m in range(1, 13)}
    entries_by_category: dict[str, list[FinanceIncomeEntry]] = {
        cat: [] for cat in INCOME_CATEGORIES
    }
    for entry in entries:
        entries_by_month[entry.month].append(entry)
        category = entry.category if entry.category in INCOME_CATEGORIES else "Outros"
        entries_by_category.setdefault(category, []).append(entry)

    visible_entries = entries
    if selected_month is not None:
        visible_entries = entries_by_month.get(selected_month, [])

    return {
        "year": year,
        "selected_month": selected_month,
        "entries": visible_entries,
        "all_entries": entries,
        "entries_by_month": entries_by_month,
        "entries_by_category": entries_by_category,
        "income_categories": INCOME_CATEGORIES,
        "category_month_totals": category_month_totals,
        "category_year_totals": category_year_totals,
        "month_labels": MONTH_LABELS,
        "month_totals": month_totals,
        "monthly_chart": build_monthly_chart(
            month_totals,
            year=year,
            selected_month=selected_month,
            link_base="/finance/income",
            variant="income",
            aria_label="Income by month",
        ),
        "year_total": sum(month_totals.values(), start=Decimal("0")),
    }


def _category_totals_for_period(
    category_month_totals: dict[str, dict[int, Decimal]],
    category_year_totals: dict[str, Decimal],
    categories: dict[str, list[FinanceExpenseEntry]],
    *,
    selected_month: int | None,
) -> list[dict[str, object]]:
    rows: list[tuple[str, Decimal]] = []
    for category in EXPENSE_CATEGORIES:
        if selected_month is not None:
            total = category_month_totals.get(category, {}).get(
                selected_month, Decimal("0")
            )
        else:
            total = category_year_totals.get(category, Decimal("0"))
        if total != 0:
            rows.append((category, total))
    rows.sort(key=lambda item: item[1])

    period_total = sum((total for _, total in rows), start=Decimal("0"))
    breakdown: list[dict[str, object]] = []
    for category, total in rows:
        pct = Decimal("0")
        if period_total != 0:
            pct = (abs(total) / abs(period_total) * Decimal("100")).quantize(
                Decimal("0.1")
            )
        breakdown.append(
            {
                "category": category,
                "slug": expense_category_slug(category),
                "total": total,
                "pct": pct,
                "count": len(categories.get(category, [])),
            }
        )
    return breakdown


def _payment_account_totals_for_period(
    payment_totals: dict[str, MonthAmounts],
    entries: list[FinanceExpenseEntry],
    *,
    selected_month: int | None,
) -> list[dict[str, object]]:
    rows: list[tuple[str, Decimal]] = []
    for account in PAYMENT_ACCOUNTS:
        if selected_month is not None:
            total = payment_totals[account].get(selected_month)
        else:
            total = payment_totals[account].total()
        if total != 0:
            rows.append((account, total))
    rows.sort(key=lambda item: item[1])

    period_total = sum((total for _, total in rows), start=Decimal("0"))
    breakdown: list[dict[str, object]] = []
    for account, total in rows:
        pct = Decimal("0")
        if period_total != 0:
            pct = (abs(total) / abs(period_total) * Decimal("100")).quantize(
                Decimal("0.1")
            )
        count = sum(
            1
            for entry in entries
            if entry.payment_account == account
            and (selected_month is None or entry.month == selected_month)
        )
        breakdown.append(
            {
                "account": account,
                "total": total,
                "pct": pct,
                "count": count,
            }
        )
    return breakdown


def build_expenses_context(
    session: Session, user_id: UUID, year: int, *, selected_month: int | None = None
) -> dict:
    entries = _load_expense_entries(session, user_id, year)
    month_totals = _sum_expenses_by_month(entries)
    payment_totals: dict[str, MonthAmounts] = {
        account: MonthAmounts() for account in PAYMENT_ACCOUNTS
    }
    for entry in entries:
        if entry.payment_account in payment_totals:
            current = payment_totals[entry.payment_account].get(entry.month)
            payment_totals[entry.payment_account].set(
                entry.month, current + effective_expense_amount(entry)
            )

    categories: dict[str, list[FinanceExpenseEntry]] = {cat: [] for cat in EXPENSE_CATEGORIES}
    for entry in entries:
        categories.setdefault(entry.category, []).append(entry)

    category_month_totals: dict[str, dict[int, Decimal]] = {}
    category_year_totals: dict[str, Decimal] = {}
    for category, category_entries in categories.items():
        month_map = _sum_expenses_by_month(category_entries)
        category_month_totals[category] = month_map
        category_year_totals[category] = sum(month_map.values(), start=Decimal("0"))

    visible_entries = entries
    if selected_month is not None:
        visible_entries = [entry for entry in entries if entry.month == selected_month]

    visible_categories: dict[str, list[FinanceExpenseEntry]] = {
        cat: [] for cat in EXPENSE_CATEGORIES
    }
    for entry in visible_entries:
        visible_categories.setdefault(entry.category, []).append(entry)

    link_targets: dict[UUID, list[FinanceExpenseEntry]] = {}
    for entry in visible_entries:
        if is_expense_reversal(entry):
            link_targets[entry.id] = linkable_expenses_for_reversal(entry, entries)

    month_payment_totals: dict[str, Decimal] = {
        account: Decimal("0") for account in PAYMENT_ACCOUNTS
    }
    if selected_month is not None:
        for account in PAYMENT_ACCOUNTS:
            month_payment_totals[account] = payment_totals[account].get(selected_month)
    else:
        for account in PAYMENT_ACCOUNTS:
            month_payment_totals[account] = payment_totals[account].total()

    return {
        "year": year,
        "selected_month": selected_month,
        "entries": visible_entries,
        "all_entries": entries,
        "categories": visible_categories,
        "all_categories": categories,
        "category_month_totals": category_month_totals,
        "category_year_totals": category_year_totals,
        "category_totals": _category_totals_for_period(
            category_month_totals,
            category_year_totals,
            categories if selected_month is None else visible_categories,
            selected_month=selected_month,
        ),
        "expense_categories": EXPENSE_CATEGORIES,
        "bills_subcategories": BILLS_SUBCATEGORIES,
        "bills_category": BILLS_CATEGORY,
        "payment_accounts": PAYMENT_ACCOUNTS,
        "payment_totals": payment_totals,
        "month_payment_totals": month_payment_totals,
        "payment_account_totals": _payment_account_totals_for_period(
            payment_totals,
            entries,
            selected_month=selected_month,
        ),
        "month_labels": MONTH_LABELS,
        "month_totals": month_totals,
        "monthly_chart": build_monthly_chart(
            month_totals,
            year=year,
            selected_month=selected_month,
            link_base="/finance/expenses",
            variant="expense",
            aria_label="Expenses by month",
        ),
        "year_total": sum(month_totals.values(), start=Decimal("0")),
        "link_targets": link_targets,
        "show_month_column": selected_month is None,
    }


def build_summary_context(
    session: Session, user_id: UUID, year: int, *, selected_month: int | None = None
) -> dict:
    income_entries = _load_income_entries(session, user_id, year)
    expense_entries = _load_expense_entries(session, user_id, year)
    transfer_entries = _load_transfer_entries(session, user_id, year)
    transfer_lookup = _transfer_amounts_lookup(transfer_entries)

    income_by_month = _sum_by_month(income_entries)
    expense_by_month = _sum_expenses_by_month(expense_entries)
    income_by_category = _sum_income_by_category(income_entries)
    bills_by_vendor = _sum_bills_by_vendor(expense_entries)
    bills_by_month = _sum_bills_by_month(expense_entries)
    day_to_day_by_account = _sum_expenses_excluding_bills(expense_entries)
    day_to_day_by_month = _sum_day_to_day_by_month(expense_entries)

    active_months = _active_month_count_from_entries(
        year, income_by_month, expense_by_month
    )
    month = resolve_month(selected_month, year)

    month_income = income_by_month[month]
    month_bills = bills_by_month[month]
    month_day_to_day = day_to_day_by_month[month]
    month_expenses = month_bills + month_day_to_day
    month_balance = month_income + month_expenses

    year_income = sum(income_by_month.values(), start=Decimal("0"))
    year_expenses = sum(expense_by_month.values(), start=Decimal("0"))
    year_balance = year_income + year_expenses

    balance_by_month = {
        month_index: income_by_month[month_index] + expense_by_month[month_index]
        for month_index in range(1, 13)
    }

    income_lines = _card_lines_for_month(
        income_by_category,
        month,
        ordered_keys=INCOME_CATEGORIES,
    )
    bills_lines = _card_lines_for_month(bills_by_vendor, month, always_paid=True)
    day_to_day_lines = _card_lines_for_month(
        day_to_day_by_account,
        month,
        ordered_keys=PAYMENT_ACCOUNTS,
        paid_for_line=lambda account, amount: _day_to_day_line_is_paid(
            month, account, amount, transfer_lookup
        ),
    )

    summary_cards = [
        {
            "id": "income",
            "variant": "income",
            "title": "Income",
            "subtitle": "PJ and other inflows",
            "total_label": "Total income",
            "total_amount": month_income,
            "lines": income_lines,
            "manage_href": f"/finance/income?year={year}&month={month}",
            "manage_label": "Manage income",
        },
        {
            "id": "bills",
            "variant": "bills",
            "title": "Bills",
            "subtitle": "Rent, utilities, and fixed household costs",
            "total_label": "Total bills",
            "total_amount": month_bills,
            "lines": bills_lines,
            "shows_payment_status": True,
            "manage_href": f"/finance/expenses?year={year}&month={month}",
            "manage_label": "Manage expenses",
        },
        {
            "id": "day-to-day",
            "variant": "day-to-day",
            "title": "Day-to-day",
            "subtitle": "Cards, debit, and cash",
            "total_label": "Total day-to-day",
            "total_amount": month_day_to_day,
            "lines": day_to_day_lines,
            "shows_payment_status": True,
            "manage_href": f"/finance/expenses?year={year}&month={month}",
            "manage_label": "Manage expenses",
        },
    ]

    return {
        "year": year,
        "selected_month": month,
        "month_labels": MONTH_LABELS,
        "summary_cards": summary_cards,
        "active_months": active_months,
        "month_income": month_income,
        "month_expenses": month_expenses,
        "month_balance": month_balance,
        "year_income": year_income,
        "year_expenses": year_expenses,
        "year_balance": year_balance,
        "month_activity": {
            month_index: month_has_activity(income_by_month[month_index])
            or month_has_activity(expense_by_month[month_index])
            for month_index in range(1, 13)
        },
        "balance_by_month": balance_by_month,
        "monthly_chart": build_summary_monthly_chart(
            income_by_month,
            expense_by_month,
            balance_by_month,
            year=year,
            selected_month=month,
            link_base="/finance/summary",
            aria_label="Income, expenses, and balance by month",
        ),
    }


def _sum_investments_by_broker(
    entries: list[FinanceInvestmentEntry],
) -> dict[str, dict[int, Decimal]]:
    totals = {broker: _empty_month_map() for broker, _ in INVESTMENT_BROKERS}
    for entry in entries:
        if entry.broker in totals:
            totals[entry.broker][entry.month] += entry.amount
    return totals


def build_investments_context(
    session: Session, user_id: UUID, year: int, *, selected_month: int | None = None
) -> dict:
    income_entries = _load_income_entries(session, user_id, year)
    investment_entries = _load_investment_entries(session, user_id, year)
    investments_by_broker = _sum_investments_by_broker(investment_entries)

    month_invested_map = _empty_month_map()
    for entry in investment_entries:
        month_invested_map[entry.month] += entry.amount

    month = resolve_month(selected_month, year)
    year_income = sum((entry.amount for entry in income_entries), start=Decimal("0"))
    annual_target = year_income * INVESTMENT_TARGET_RATE
    ytd_invested = sum(
        (
            entry.amount
            for entry in investment_entries
            if entry.month <= month
        ),
        start=Decimal("0"),
    )
    month_invested = month_invested_map[month]
    year_invested = sum(month_invested_map.values(), start=Decimal("0"))

    broker_lines: list[dict[str, object]] = []
    for broker_key, broker_label in INVESTMENT_BROKERS:
        amount = investments_by_broker[broker_key].get(month, Decimal("0"))
        if amount != 0:
            broker_lines.append({"broker": broker_key, "label": broker_label, "amount": amount})

    entries_by_month: dict[int, list[FinanceInvestmentEntry]] = {m: [] for m in range(1, 13)}
    for entry in investment_entries:
        entries_by_month[entry.month].append(entry)

    visible_entries = investment_entries
    if selected_month is not None:
        visible_entries = entries_by_month.get(month, [])

    return {
        "year": year,
        "selected_month": selected_month if selected_month is not None else month,
        "month_labels": MONTH_LABELS,
        "entries": visible_entries,
        "all_entries": investment_entries,
        "entries_by_month": entries_by_month,
        "investment_brokers": INVESTMENT_BROKERS,
        "broker_lines": broker_lines,
        "investments_by_broker": investments_by_broker,
        "annual_target": annual_target,
        "ytd_invested": ytd_invested,
        "month_invested": month_invested,
        "year_invested": year_invested,
        "year_income": year_income,
        "month_totals": month_invested_map,
        "monthly_chart": build_monthly_chart(
            month_invested_map,
            year=year,
            selected_month=selected_month,
            link_base="/finance/investments",
            variant="income",
            aria_label="Investments by month",
        ),
    }


def upsert_investment_entry(
    session: Session,
    user_id: UUID,
    year: int,
    month: int,
    broker: str,
    amount: Decimal,
) -> FinanceInvestmentEntry | None:
    validate_investment_broker(broker)
    if amount < 0:
        raise ValueError("Amount cannot be negative.")

    existing = session.exec(
        select(FinanceInvestmentEntry)
        .where(FinanceInvestmentEntry.user_id == user_id)
        .where(FinanceInvestmentEntry.year == year)
        .where(FinanceInvestmentEntry.month == month)
        .where(FinanceInvestmentEntry.broker == broker)
    ).first()

    if amount == 0:
        if existing:
            session.delete(existing)
            session.commit()
        return None

    if existing:
        existing.amount = amount
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    entry = FinanceInvestmentEntry(
        user_id=user_id,
        year=year,
        month=month,
        broker=broker,
        amount=amount,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def build_transfers_context(
    session: Session, user_id: UUID, year: int, *, selected_month: int | None = None
) -> dict:
    entries = _load_transfer_entries(session, user_id, year)
    month_totals = _sum_by_month(entries)
    entries_by_month: dict[int, list[FinanceTransferEntry]] = {m: [] for m in range(1, 13)}
    for entry in entries:
        entries_by_month[entry.month].append(entry)

    visible_entries = entries
    if selected_month is not None:
        visible_entries = entries_by_month.get(selected_month, [])

    return {
        "year": year,
        "selected_month": selected_month,
        "entries": visible_entries,
        "all_entries": entries,
        "entries_by_month": entries_by_month,
        "transfer_accounts": TRANSFER_ACCOUNTS,
        "month_labels": MONTH_LABELS,
        "month_totals": month_totals,
        "monthly_chart": build_monthly_chart(
            month_totals,
            year=year,
            selected_month=selected_month,
            link_base="/finance/transfers",
            variant="income",
            aria_label="Transfers by month",
        ),
        "year_total": sum(month_totals.values(), start=Decimal("0")),
    }


def advance_finance_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def split_installment_amounts(total: Decimal, count: int) -> list[Decimal]:
    if count <= 1:
        return [total]

    sign = Decimal("-1") if total < 0 else Decimal("1")
    abs_total = abs(total)
    base = (abs_total / Decimal(count)).quantize(Decimal("0.01"))
    amounts = [base] * count
    remainder = abs_total - sum(amounts)
    if remainder != 0:
        amounts[-1] += remainder
    return [sign * amount for amount in amounts]


def installment_vendor_label(vendor: str, index: int, total: int) -> str:
    if total <= 1:
        return vendor
    return f"{vendor} ({index}/{total})"


def build_expense_entries(
    *,
    user_id: UUID,
    year: int,
    month: int,
    category: str,
    vendor: str,
    payment_account: str,
    amount: Decimal,
    installments: int = 1,
    transaction_date: date | None = None,
    subcategory: str | None = None,
) -> list[FinanceExpenseEntry]:
    if installments < 1 or installments > MAX_EXPENSE_INSTALLMENTS:
        raise ValueError(
            f"Installments must be between 1 and {MAX_EXPENSE_INSTALLMENTS}."
        )

    amounts = split_installment_amounts(amount, installments)
    entries: list[FinanceExpenseEntry] = []
    entry_year, entry_month = year, month
    for index, installment_amount in enumerate(amounts, start=1):
        entries.append(
            FinanceExpenseEntry(
                user_id=user_id,
                year=entry_year,
                month=entry_month,
                transaction_date=transaction_date if index == 1 else None,
                category=category,
                vendor=installment_vendor_label(vendor, index, installments),
                payment_account=payment_account,
                amount=installment_amount,
                subcategory=subcategory,
            )
        )
        entry_year, entry_month = advance_finance_month(entry_year, entry_month)
    return entries


def create_expense_entries(
    session: Session,
    *,
    user_id: UUID,
    year: int,
    month: int,
    category: str,
    vendor: str,
    payment_account: str,
    amount: Decimal,
    installments: int = 1,
    transaction_date: date | None = None,
    subcategory: str | None = None,
) -> list[FinanceExpenseEntry]:
    entries = build_expense_entries(
        user_id=user_id,
        year=year,
        month=month,
        category=category,
        vendor=vendor.strip(),
        payment_account=payment_account,
        amount=amount,
        installments=installments,
        transaction_date=transaction_date,
        subcategory=subcategory,
    )
    for entry in entries:
        session.add(entry)
    return entries


LEGACY_PJ_SUMMARY_KEYS = frozenset({"pro_labore", "lucro"})
PJ_SUMMARY_KEY = "pj"
LEGACY_POUANCA_SUMMARY_KEY = "poupanca"


def migrate_pro_labore_lucro_to_pj(session: Session) -> int:
    """Legacy migration helper for alembic 026 (pre-refactor summary table)."""
    from uuid import uuid4

    from sqlalchemy import text

    rows = _load_legacy_summary_rows(session)
    legacy_rows = [row for row in rows if row.line_key in LEGACY_PJ_SUMMARY_KEYS]
    if not legacy_rows:
        return 0

    bind = session.get_bind()
    merged: dict[tuple[UUID, int, int], Decimal] = {}
    for row in legacy_rows:
        key = (row.user_id, row.year, row.month)
        merged[key] = merged.get(key, Decimal("0")) + row.amount

    bind.execute(
        text(
            "DELETE FROM finance_summary_amounts "
            "WHERE line_key IN ('pro_labore', 'lucro')"
        )
    )

    for (user_id, year, month), amount in merged.items():
        bind.execute(
            text(
                "DELETE FROM finance_summary_amounts "
                "WHERE user_id = :user_id AND year = :year AND month = :month "
                "AND line_key = :line_key"
            ),
            {
                "user_id": user_id,
                "year": year,
                "month": month,
                "line_key": PJ_SUMMARY_KEY,
            },
        )
        bind.execute(
            text(
                "INSERT INTO finance_summary_amounts "
                "(id, user_id, year, month, line_key, amount, created_at, updated_at) "
                "VALUES (:id, :user_id, :year, :month, :line_key, :amount, "
                "datetime('now'), datetime('now'))"
            ),
            {
                "id": uuid4(),
                "user_id": user_id,
                "year": year,
                "month": month,
                "line_key": PJ_SUMMARY_KEY,
                "amount": amount,
            },
        )

    session.commit()
    return len(merged)


def remove_poupanca_summary_lines(session: Session) -> int:
    """Legacy migration helper for alembic 027 (pre-refactor summary table)."""
    from sqlalchemy import text

    bind = session.get_bind()
    result = bind.execute(
        text("DELETE FROM finance_summary_amounts WHERE line_key = :line_key"),
        {"line_key": LEGACY_POUANCA_SUMMARY_KEY},
    )
    session.commit()
    return result.rowcount or 0
