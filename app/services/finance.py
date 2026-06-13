from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, select
from sqlalchemy import nulls_last

from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceSummaryAmount,
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

EXPENSE_CATEGORIES = (
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
)

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

MAX_EXPENSE_INSTALLMENTS = 48

DEBIT_PAYMENT_ACCOUNTS = frozenset({"BB Débito", "Nuconta", "Wise"})

INCOME_SUMMARY_LINES = (
    ("pj", "PJ"),
    ("outros", "Outros"),
)

EXPENSE_CONTAS_LINES = (
    ("aluguel", "Aluguel"),
    ("internet", "Internet"),
    ("luz", "Luz"),
    ("gas", "Gás"),
)

EXPENSE_REGULAR_LINES = (
    ("regular_outros", "Outros"),
    ("cc_ourocard", "CC (Ourocard)"),
    ("cc_nubank", "CC (Nubank)"),
    ("cc_xp", "CC (XP)"),
    ("debito", "Débito (BB + Nuconta + Wise)"),
    ("dinheiro", "Dinheiro"),
)

INVESTMENT_LINES = (
    ("inv_xp", "XP"),
    ("inv_ib", "IB"),
    ("inv_nubank", "Nubank"),
    ("inv_mb", "MB"),
)

MANUAL_SUMMARY_KEYS = frozenset(
    key
    for key, _ in (
        *INCOME_SUMMARY_LINES,
        *EXPENSE_CONTAS_LINES,
        *EXPENSE_REGULAR_LINES,
        *INVESTMENT_LINES,
    )
    if key not in {"outros", "debito", "dinheiro"}
)

BILL_SUMMARY_KEYS = frozenset(key for key, _ in EXPENSE_CONTAS_LINES)

SUMMARY_SECTION_LINE_KEYS: dict[str, tuple[str, ...]] = {
    "income": tuple(
        key for key, _ in INCOME_SUMMARY_LINES if key in MANUAL_SUMMARY_KEYS
    ),
    "expenses-contas": tuple(key for key, _ in EXPENSE_CONTAS_LINES),
    "expenses-regular": tuple(
        key for key, _ in EXPENSE_REGULAR_LINES if key in MANUAL_SUMMARY_KEYS
    ),
    "investments": tuple(key for key, _ in INVESTMENT_LINES),
}


def normalize_vendor_key(vendor: str) -> str:
    name = vendor.strip()
    if "|" in name:
        name = name.split("|", 1)[1].strip()
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


def save_vendor_category(
    session: Session,
    user_id: UUID,
    vendor: str,
    category: str,
) -> None:
    if category not in EXPENSE_CATEGORIES:
        return
    vendor_key = normalize_vendor_key(vendor)
    if not vendor_key or vendor_key == "unknown":
        return

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
            )
        )
        return

    if existing.category != category:
        existing.category = category
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


def normalize_summary_amount(line_key: str, amount: Decimal) -> Decimal:
    if line_key in BILL_SUMMARY_KEYS:
        if amount == 0:
            return Decimal("0")
        return -abs(amount)
    return amount


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


@dataclass
class SummaryRow:
    key: str
    label: str
    amounts: MonthAmounts
    editable: bool = False
    section: str = ""
    is_total: bool = False
    is_section_header: bool = False

    @property
    def year_total(self) -> Decimal:
        return self.amounts.total()

    @property
    def year_average(self) -> Decimal:
        return self.amounts.total() / Decimal("12")


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


def _load_summary_amounts(
    session: Session, user_id: UUID, year: int
) -> dict[tuple[str, int], Decimal]:
    rows = session.exec(
        select(FinanceSummaryAmount)
        .where(FinanceSummaryAmount.user_id == user_id)
        .where(FinanceSummaryAmount.year == year)
    ).all()
    return {(row.line_key, row.month): row.amount for row in rows}


def _sum_by_month(
    entries: list[FinanceIncomeEntry] | list[FinanceExpenseEntry],
) -> dict[int, Decimal]:
    totals = _empty_month_map()
    for entry in entries:
        totals[entry.month] += entry.amount
    return totals


def _sum_expenses_by_payment(
    entries: list[FinanceExpenseEntry], accounts: frozenset[str]
) -> dict[int, Decimal]:
    totals = _empty_month_map()
    for entry in entries:
        if entry.payment_account in accounts:
            totals[entry.month] += entry.amount
    return totals


def _manual_amounts(
    summary_values: dict[tuple[str, int], Decimal], line_key: str
) -> MonthAmounts:
    amounts = MonthAmounts()
    for month in range(1, 13):
        amounts.set(month, summary_values.get((line_key, month), Decimal("0")))
    return amounts


def _active_month_count(
    year: int,
    income_by_month: dict[int, Decimal],
    expense_by_month: dict[int, Decimal],
    summary_values: dict[tuple[str, int], Decimal],
) -> int:
    active = set()
    for month in range(1, 13):
        if income_by_month[month] != 0 or expense_by_month[month] != 0:
            active.add(month)
        for (_, month_key), amount in summary_values.items():
            if month_key == month and amount != 0:
                active.add(month)
    if year == date.today().year:
        active = {m for m in active if m <= date.today().month}
    return max(len(active), 1)


def build_income_context(
    session: Session, user_id: UUID, year: int, *, selected_month: int | None = None
) -> dict:
    entries = _load_income_entries(session, user_id, year)
    month_totals = _sum_by_month(entries)
    entries_by_month: dict[int, list[FinanceIncomeEntry]] = {m: [] for m in range(1, 13)}
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
    month_totals = _sum_by_month(entries)
    payment_totals: dict[str, MonthAmounts] = {
        account: MonthAmounts() for account in PAYMENT_ACCOUNTS
    }
    for entry in entries:
        if entry.payment_account in payment_totals:
            current = payment_totals[entry.payment_account].get(entry.month)
            payment_totals[entry.payment_account].set(entry.month, current + entry.amount)

    categories: dict[str, list[FinanceExpenseEntry]] = {cat: [] for cat in EXPENSE_CATEGORIES}
    for entry in entries:
        categories.setdefault(entry.category, []).append(entry)

    category_month_totals: dict[str, dict[int, Decimal]] = {}
    category_year_totals: dict[str, Decimal] = {}
    for category, category_entries in categories.items():
        month_map = _sum_by_month(category_entries)
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
    summary_values = _load_summary_amounts(session, user_id, year)

    income_by_month = _sum_by_month(income_entries)
    expense_by_month = _sum_by_month(expense_entries)
    debit_by_month = _sum_expenses_by_payment(expense_entries, DEBIT_PAYMENT_ACCOUNTS)
    cash_by_month = _sum_expenses_by_payment(expense_entries, frozenset({"Dinheiro"}))

    active_months = _active_month_count(
        year, income_by_month, expense_by_month, summary_values
    )

    rows: list[SummaryRow] = []

    income_lines: dict[str, MonthAmounts] = {}
    for key, label in INCOME_SUMMARY_LINES:
        if key == "outros":
            amounts = MonthAmounts()
            for month in range(1, 13):
                amounts.set(month, income_by_month[month])
            income_lines[key] = amounts
            rows.append(
                SummaryRow(
                    key=key,
                    label=label,
                    amounts=amounts,
                    editable=False,
                    section="income",
                )
            )
        else:
            amounts = _manual_amounts(summary_values, key)
            income_lines[key] = amounts
            rows.append(
                SummaryRow(
                    key=key,
                    label=label,
                    amounts=amounts,
                    editable=True,
                    section="income",
                )
            )

    income_total = MonthAmounts()
    for month in range(1, 13):
        income_total.set(
            month,
            sum(income_lines[key].get(month) for key, _ in INCOME_SUMMARY_LINES),
        )
    rows.insert(
        0,
        SummaryRow(
            key="income_total",
            label="INCOME",
            amounts=income_total,
            section="income",
            is_total=True,
        ),
    )

    expense_contas_lines: dict[str, MonthAmounts] = {}
    rows.append(
        SummaryRow(
            key="expenses_header",
            label="EXPENSES",
            amounts=MonthAmounts(),
            section="expenses",
            is_section_header=True,
        )
    )
    rows.append(
        SummaryRow(
            key="contas_header",
            label="Contas",
            amounts=MonthAmounts(),
            section="expenses",
            is_section_header=True,
        )
    )
    for key, label in EXPENSE_CONTAS_LINES:
        amounts = _manual_amounts(summary_values, key)
        expense_contas_lines[key] = amounts
        rows.append(
            SummaryRow(
                key=key,
                label=label,
                amounts=amounts,
                editable=True,
                section="expenses_contas",
            )
        )

    contas_total = MonthAmounts()
    for month in range(1, 13):
        contas_total.set(
            month,
            sum(line.get(month) for line in expense_contas_lines.values()),
        )
    rows.append(
        SummaryRow(
            key="contas_total",
            label="Contas",
            amounts=contas_total,
            section="expenses_contas",
            is_total=True,
        )
    )

    rows.append(
        SummaryRow(
            key="regular_header",
            label="Regular",
            amounts=MonthAmounts(),
            section="expenses",
            is_section_header=True,
        )
    )

    expense_regular_lines: dict[str, MonthAmounts] = {}
    for key, label in EXPENSE_REGULAR_LINES:
        if key == "debito":
            amounts = MonthAmounts()
            for month in range(1, 13):
                amounts.set(month, debit_by_month[month])
            editable = False
        elif key == "dinheiro":
            amounts = MonthAmounts()
            for month in range(1, 13):
                amounts.set(month, cash_by_month[month])
            editable = False
        else:
            amounts = _manual_amounts(summary_values, key)
            editable = True
        expense_regular_lines[key] = amounts
        rows.append(
            SummaryRow(
                key=key,
                label=label,
                amounts=amounts,
                editable=editable,
                section="expenses_regular",
            )
        )

    regular_total = MonthAmounts()
    for month in range(1, 13):
        regular_total.set(
            month,
            sum(line.get(month) for line in expense_regular_lines.values()),
        )
    rows.append(
        SummaryRow(
            key="regular_total",
            label="Regular",
            amounts=regular_total,
            section="expenses_regular",
            is_total=True,
        )
    )

    expenses_total = MonthAmounts()
    for month in range(1, 13):
        expenses_total.set(month, contas_total.get(month) + regular_total.get(month))
    rows.append(
        SummaryRow(
            key="expenses_total",
            label="EXPENSES",
            amounts=expenses_total,
            section="expenses",
            is_total=True,
        )
    )

    balance = MonthAmounts()
    for month in range(1, 13):
        balance.set(month, income_total.get(month) + expenses_total.get(month))
    rows.append(
        SummaryRow(
            key="balance",
            label="SALDO",
            amounts=balance,
            section="balance",
            is_total=True,
        )
    )

    rows.append(
        SummaryRow(
            key="investments_header",
            label="INVESTMENTS",
            amounts=MonthAmounts(),
            section="investments",
            is_section_header=True,
        )
    )

    investment_target = MonthAmounts()
    for month in range(1, 13):
        investment_target.set(month, income_total.get(month) * Decimal("0.30"))

    invested_total = MonthAmounts()
    broker_rows: list[SummaryRow] = []
    for key, label in INVESTMENT_LINES:
        amounts = _manual_amounts(summary_values, key)
        broker_rows.append(
            SummaryRow(
                key=key,
                label=label,
                amounts=amounts,
                editable=True,
                section="investments",
            )
        )
        for month in range(1, 13):
            invested_total.set(
                month, invested_total.get(month) + amounts.get(month)
            )

    investment_gap = MonthAmounts()
    cumulative_gap = Decimal("0")
    for month in range(1, 13):
        month_gap = investment_target.get(month) - invested_total.get(month)
        cumulative_gap += month_gap
        investment_gap.set(month, cumulative_gap)

    rows.extend(
        [
            SummaryRow(
                key="investment_gap",
                label="INVESTMENTS",
                amounts=investment_gap,
                section="investments",
                is_total=True,
            ),
            SummaryRow(
                key="investment_target",
                label="Meta = 30% INCOME",
                amounts=investment_target,
                section="investments",
            ),
            SummaryRow(
                key="invested_total",
                label="Investido",
                amounts=invested_total,
                section="investments",
                is_total=True,
            ),
            *broker_rows,
        ]
    )

    rows_by_key = {row.key: row for row in rows}
    balance_by_month = {
        month_index: rows_by_key["balance"].amounts.get(month_index)
        for month_index in range(1, 13)
    }
    month = resolve_month(selected_month, year)
    month_income = rows_by_key["income_total"].amounts.get(month)
    month_expenses = rows_by_key["expenses_total"].amounts.get(month)
    month_balance = rows_by_key["balance"].amounts.get(month)
    year_income = rows_by_key["income_total"].year_total
    year_expenses = rows_by_key["expenses_total"].year_total
    year_balance = rows_by_key["balance"].year_total

    investment_target_month = investment_target.get(month)
    invested_total_month = invested_total.get(month)
    contas_total_month = contas_total.get(month)
    regular_total_month = regular_total.get(month)
    summary_sections = [
        {
            "id": "income",
            "title": "Income",
            "subtitle": "Salary, profit, and other inflows",
            "total_label": "Total income",
            "total_amount": month_income,
            "manage_href": f"/finance/income?year={year}&month={month}",
            "manage_label": "Manage income",
            "rows": [
                row
                for row in rows
                if row.section == "income" and not row.is_total and not row.is_section_header
            ],
        },
        {
            "id": "expenses-contas",
            "title": "Bills",
            "subtitle": "Rent, utilities, and fixed household costs",
            "total_label": "Total bills",
            "total_amount": contas_total_month,
            "manage_href": f"/finance/expenses?year={year}&month={month}",
            "manage_label": "Manage expenses",
            "rows": [
                row
                for row in rows
                if row.section == "expenses_contas" and not row.is_total
            ],
        },
        {
            "id": "expenses-regular",
            "title": "Day-to-day",
            "subtitle": "Cards, debit, and cash",
            "total_label": "Total day-to-day",
            "total_amount": regular_total_month,
            "manage_href": f"/finance/expenses?year={year}&month={month}",
            "manage_label": "Manage expenses",
            "rows": [
                row
                for row in rows
                if row.section == "expenses_regular" and not row.is_total
            ],
        },
        {
            "id": "investments",
            "title": "Investments",
            "subtitle": "30% income target and broker allocations",
            "total_label": "Invested this month",
            "total_amount": invested_total_month,
            "manage_href": "/portfolio/investments",
            "manage_label": "Manage portfolio",
            "progress_target": investment_target_month,
            "progress_invested": invested_total_month,
            "rows": [
                row
                for row in rows
                if row.section == "investments"
                and not row.is_section_header
                and row.key not in {"investment_gap"}
            ],
        },
    ]

    return {
        "year": year,
        "selected_month": month,
        "month_labels": MONTH_LABELS,
        "rows": rows,
        "rows_by_key": rows_by_key,
        "summary_sections": summary_sections,
        "active_months": active_months,
        "income_tab_total": income_by_month[month],
        "expense_tab_total": expense_by_month[month],
        "income_tab_year_total": sum(income_by_month.values(), start=Decimal("0")),
        "expense_tab_year_total": sum(expense_by_month.values(), start=Decimal("0")),
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
        "monthly_chart": build_monthly_chart(
            balance_by_month,
            year=year,
            selected_month=month,
            link_base="/finance/summary",
            variant="balance",
            aria_label="Balance by month",
        ),
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
    )
    for entry in entries:
        session.add(entry)
    return entries


def _apply_summary_amount(
    session: Session,
    user_id: UUID,
    year: int,
    month: int,
    line_key: str,
    amount: Decimal,
) -> None:
    existing = session.exec(
        select(FinanceSummaryAmount)
        .where(FinanceSummaryAmount.user_id == user_id)
        .where(FinanceSummaryAmount.year == year)
        .where(FinanceSummaryAmount.month == month)
        .where(FinanceSummaryAmount.line_key == line_key)
    ).first()

    if existing:
        existing.amount = amount
        session.add(existing)
    else:
        session.add(
            FinanceSummaryAmount(
                user_id=user_id,
                year=year,
                month=month,
                line_key=line_key,
                amount=amount,
            )
        )


LEGACY_PJ_SUMMARY_KEYS = frozenset({"pro_labore", "lucro"})
PJ_SUMMARY_KEY = "pj"
LEGACY_POUANCA_SUMMARY_KEY = "poupanca"


def migrate_pro_labore_lucro_to_pj(session: Session) -> int:
    legacy_rows = session.exec(
        select(FinanceSummaryAmount).where(
            FinanceSummaryAmount.line_key.in_(LEGACY_PJ_SUMMARY_KEYS)
        )
    ).all()
    if not legacy_rows:
        return 0

    merged: dict[tuple[UUID, int, int], Decimal] = {}
    for row in legacy_rows:
        key = (row.user_id, row.year, row.month)
        merged[key] = merged.get(key, Decimal("0")) + row.amount

    for row in legacy_rows:
        session.delete(row)

    for (user_id, year, month), amount in merged.items():
        existing = session.exec(
            select(FinanceSummaryAmount)
            .where(FinanceSummaryAmount.user_id == user_id)
            .where(FinanceSummaryAmount.year == year)
            .where(FinanceSummaryAmount.month == month)
            .where(FinanceSummaryAmount.line_key == PJ_SUMMARY_KEY)
        ).first()
        if existing:
            existing.amount = amount
            session.add(existing)
        else:
            session.add(
                FinanceSummaryAmount(
                    user_id=user_id,
                    year=year,
                    month=month,
                    line_key=PJ_SUMMARY_KEY,
                    amount=amount,
                )
            )

    session.commit()
    return len(merged)


def remove_poupanca_summary_lines(session: Session) -> int:
    rows = session.exec(
        select(FinanceSummaryAmount).where(
            FinanceSummaryAmount.line_key == LEGACY_POUANCA_SUMMARY_KEY
        )
    ).all()
    for row in rows:
        session.delete(row)
    if rows:
        session.commit()
    return len(rows)


def upsert_summary_amount(
    session: Session,
    user_id: UUID,
    year: int,
    month: int,
    line_key: str,
    amount: Decimal,
) -> None:
    if line_key not in MANUAL_SUMMARY_KEYS:
        raise ValueError(f"Line {line_key} is not editable")

    amount = normalize_summary_amount(line_key, amount)
    _apply_summary_amount(session, user_id, year, month, line_key, amount)
    session.commit()


def upsert_summary_section(
    session: Session,
    user_id: UUID,
    year: int,
    month: int,
    section_id: str,
    updates: dict[str, Decimal],
) -> None:
    allowed_keys = SUMMARY_SECTION_LINE_KEYS.get(section_id)
    if allowed_keys is None:
        raise ValueError(f"Section {section_id} is not editable")

    for line_key, raw_amount in updates.items():
        if line_key not in allowed_keys:
            raise ValueError(f"Line {line_key} is not in section {section_id}.")
        amount = normalize_summary_amount(line_key, raw_amount)
        _apply_summary_amount(session, user_id, year, month, line_key, amount)

    session.commit()
