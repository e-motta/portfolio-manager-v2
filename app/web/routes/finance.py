from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import CurrentUserDep
from app.core.db import SessionDep
from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceInvestmentEntry,
    FinanceTransferEntry,
)
from app.services.finance import (
    BILLS_CATEGORY,
    BILLS_SUBCATEGORIES,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    INVESTMENT_BROKERS,
    MAX_EXPENSE_INSTALLMENTS,
    PAYMENT_ACCOUNTS,
    TRANSFER_ACCOUNTS,
    _UNSET,
    build_expenses_context,
    build_income_context,
    build_investments_context,
    build_summary_context,
    build_transfers_context,
    create_expense_entries,
    link_expense_reversal,
    load_vendor_rule_map,
    resolve_expense_subcategory,
    resolve_month,
    resolve_year,
    save_vendor_category,
    upsert_investment_entry,
    validate_income_category,
    validate_investment_broker,
    validate_transfer_accounts,
)
from app.web.dependencies import TemplatesDep

router = APIRouter(prefix="/finance", tags=["finance"])


def _parse_optional_date(value: str, field_name: str = "date") -> date | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}.",
        ) from exc


def _parse_expense_amount(value: str, field_name: str = "amount") -> Decimal:
    amount = _parse_amount(value, field_name, allow_negative=True)
    if amount == 0:
        return Decimal("0")
    return -abs(amount)


def _parse_amount(value: str, field_name: str, *, allow_negative: bool = False) -> Decimal:
    normalized = value.strip().replace(",", ".")
    try:
        amount = Decimal(normalized)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}.",
        ) from exc
    if not allow_negative and amount < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be negative.",
        )
    return amount


def _parse_month(value: str) -> int:
    try:
        month = int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid month.",
        ) from exc
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Month must be between 1 and 12.",
        )
    return month


def _parse_installments(value: str) -> int:
    normalized = value.strip()
    if not normalized:
        return 1
    try:
        count = int(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid installments.",
        ) from exc
    if count < 1 or count > MAX_EXPENSE_INSTALLMENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Installments must be between 1 and {MAX_EXPENSE_INSTALLMENTS}.",
        )
    return count


def _parse_year(value: str) -> int:
    try:
        year = int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid year.",
        ) from exc
    if year < 2000 or year > 2100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid year.",
        )
    return year


def _year_options(current_year: int) -> list[int]:
    return list(range(current_year - 2, current_year + 3))


def _finance_query(year: int, month: int | None = None) -> str:
    query = f"year={year}"
    if month is not None:
        query += f"&month={month}"
    return query


def _expense_row_context(context: dict, entry: FinanceExpenseEntry) -> dict:
    return {
        "entry": entry,
        "month_labels": context["month_labels"],
        "expense_categories": EXPENSE_CATEGORIES,
        "bills_subcategories": context.get("bills_subcategories", BILLS_SUBCATEGORIES),
        "bills_category": context.get("bills_category", BILLS_CATEGORY),
        "payment_accounts": PAYMENT_ACCOUNTS,
        "link_targets": context.get("link_targets", {}),
        "show_month_column": context.get("show_month_column", True),
    }


def _page_shell(
    context: dict,
    *,
    tab: str,
    year: int,
    selected_month: int,
    filter_month: int | None = None,
) -> dict:
    context["finance_tab"] = tab
    context["year_options"] = _year_options(year)
    context["selected_month"] = selected_month
    context["filter_month"] = filter_month
    context["form_default_month"] = filter_month or selected_month
    return context


@router.get("/summary", response_class=HTMLResponse)
def summary_page(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    year: Annotated[int | None, Query()] = None,
    month: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    selected_year = resolve_year(year)
    selected_month = resolve_month(month, selected_year)
    context = build_summary_context(
        session, current_user.id, selected_year, selected_month=selected_month
    )
    _page_shell(
        context,
        tab="summary",
        year=selected_year,
        selected_month=selected_month,
        filter_month=selected_month,
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/finance_summary.html",
        context=context,
    )


@router.get("/income", response_class=HTMLResponse)
def income_page(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    year: Annotated[int | None, Query()] = None,
    month: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    selected_year = resolve_year(year)
    filter_month = month if month is not None else None
    if filter_month is not None:
        filter_month = _parse_month(str(filter_month))
    context = build_income_context(
        session, current_user.id, selected_year, selected_month=filter_month
    )
    _page_shell(
        context,
        tab="income",
        year=selected_year,
        selected_month=resolve_month(None, selected_year),
        filter_month=filter_month,
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/finance_income.html",
        context=context,
    )


@router.post("/income", response_class=HTMLResponse)
def create_income_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    year: Annotated[str, Form()],
    month: Annotated[str, Form()],
    description: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    category: Annotated[str, Form()] = "Outros",
) -> RedirectResponse:
    try:
        parsed_category = validate_income_category(category.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    entry = FinanceIncomeEntry(
        user_id=current_user.id,
        year=_parse_year(year),
        month=_parse_month(month),
        category=parsed_category,
        description=description.strip(),
        amount=_parse_amount(amount, "amount"),
    )
    session.add(entry)
    session.commit()
    return RedirectResponse(
        url=f"/finance/income?{_finance_query(entry.year, entry.month)}",
        status_code=303,
    )


@router.post("/income/{entry_id}", response_class=HTMLResponse)
def update_income_entry(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
    month: str = Form(default=""),
    category: str = Form(default=""),
    description: str = Form(default=""),
    amount: str = Form(default=""),
) -> HTMLResponse:
    entry = session.get(FinanceIncomeEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if month:
        entry.month = _parse_month(month)
    if category:
        try:
            entry.category = validate_income_category(category.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    if description:
        entry.description = description.strip()
    if amount:
        entry.amount = _parse_amount(amount, "amount")
    entry.updated_at = datetime.utcnow()
    session.add(entry)
    session.commit()
    session.refresh(entry)

    context = build_income_context(session, current_user.id, entry.year)
    return templates.TemplateResponse(
        request=request,
        name="partials/finance_income_row.html",
        context={
            "entry": entry,
            "month_labels": context["month_labels"],
            "income_categories": INCOME_CATEGORIES,
            "show_month_column": context.get("selected_month") is None,
        },
    )


@router.delete("/income/{entry_id}", response_class=HTMLResponse)
def delete_income_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
) -> HTMLResponse:
    entry = session.get(FinanceIncomeEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(entry)
    session.commit()
    return HTMLResponse("")


@router.get("/expenses", response_class=HTMLResponse)
def expenses_page(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    year: Annotated[int | None, Query()] = None,
    month: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    selected_year = resolve_year(year)
    filter_month = month if month is not None else None
    if filter_month is not None:
        filter_month = _parse_month(str(filter_month))
    context = build_expenses_context(
        session, current_user.id, selected_year, selected_month=filter_month
    )
    _page_shell(
        context,
        tab="expenses",
        year=selected_year,
        selected_month=resolve_month(None, selected_year),
        filter_month=filter_month,
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/finance_expenses.html",
        context=context,
    )


@router.post("/expenses", response_class=HTMLResponse)
def create_expense_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    year: Annotated[str, Form()],
    month: Annotated[str, Form()],
    category: Annotated[str, Form()],
    vendor: Annotated[str, Form()],
    payment_account: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    transaction_date: Annotated[str, Form()] = "",
    installments: Annotated[str, Form()] = "",
    installments_enabled: Annotated[str, Form()] = "",
    subcategory: Annotated[str, Form()] = "",
) -> RedirectResponse:
    parsed_amount = _parse_expense_amount(amount)
    parsed_installments = (
        _parse_installments(installments)
        if installments_enabled == "1" or installments.strip()
        else 1
    )

    if category not in EXPENSE_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid category.",
        )
    if payment_account not in PAYMENT_ACCOUNTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid payment account.",
        )

    vendor_rules = load_vendor_rule_map(session, current_user.id)
    try:
        explicit = subcategory.strip() if subcategory.strip() else _UNSET
        resolved_subcategory = resolve_expense_subcategory(
            category,
            vendor,
            vendor_rules,
            explicit_subcategory=explicit,
        )
        entries = create_expense_entries(
            session,
            user_id=current_user.id,
            year=_parse_year(year),
            month=_parse_month(month),
            category=category,
            vendor=vendor,
            payment_account=payment_account,
            amount=parsed_amount,
            installments=parsed_installments,
            transaction_date=_parse_optional_date(transaction_date),
            subcategory=resolved_subcategory,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    save_vendor_category(
        session,
        current_user.id,
        vendor,
        category,
        subcategory=resolved_subcategory,
    )

    session.commit()
    first_entry = entries[0]
    return RedirectResponse(
        url=f"/finance/expenses?{_finance_query(first_entry.year, first_entry.month)}",
        status_code=303,
    )


@router.post("/expenses/{entry_id}", response_class=HTMLResponse)
def update_expense_entry(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
    month: str = Form(default=""),
    category: str = Form(default=""),
    vendor: str = Form(default=""),
    payment_account: str = Form(default=""),
    amount: str = Form(default=""),
    transaction_date: str = Form(default=""),
    subcategory: str = Form(default=""),
) -> HTMLResponse:
    entry = session.get(FinanceExpenseEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if month:
        entry.month = _parse_month(month)
    if category:
        if category not in EXPENSE_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid category.",
            )
        entry.category = category
    if vendor:
        entry.vendor = vendor.strip()
    if payment_account:
        if payment_account not in PAYMENT_ACCOUNTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid payment account.",
            )
        entry.payment_account = payment_account
    if amount:
        entry.amount = _parse_expense_amount(amount)

    vendor_rules = load_vendor_rule_map(session, current_user.id)
    try:
        if entry.category != BILLS_CATEGORY:
            entry.subcategory = None
        else:
            entry.subcategory = resolve_expense_subcategory(
                entry.category,
                entry.vendor,
                vendor_rules,
                explicit_subcategory=subcategory,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    entry.transaction_date = _parse_optional_date(transaction_date)
    entry.updated_at = datetime.utcnow()
    session.add(entry)
    save_vendor_category(
        session,
        current_user.id,
        entry.vendor,
        entry.category,
        subcategory=entry.subcategory,
    )
    session.commit()
    session.refresh(entry)

    context = build_expenses_context(session, current_user.id, entry.year)
    return templates.TemplateResponse(
        request=request,
        name="partials/finance_expense_row.html",
        context=_expense_row_context(context, entry),
    )


@router.post("/expenses/{entry_id}/link", response_class=HTMLResponse)
def link_expense_reversal_entry(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
    target_id: Annotated[str, Form()],
) -> HTMLResponse:
    try:
        parsed_target_id = UUID(target_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid target expense.",
        ) from exc

    try:
        target = link_expense_reversal(
            session,
            user_id=current_user.id,
            reversal_id=entry_id,
            target_id=parsed_target_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    session.commit()
    session.refresh(target)

    context = build_expenses_context(
        session,
        current_user.id,
        target.year,
        selected_month=target.month,
    )
    row_context = _expense_row_context(context, target)
    return templates.TemplateResponse(
        request=request,
        name="partials/finance_expense_row_oob.html",
        context=row_context,
    )


@router.delete("/expenses/{entry_id}", response_class=HTMLResponse)
def delete_expense_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
) -> HTMLResponse:
    entry = session.get(FinanceExpenseEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(entry)
    session.commit()
    return HTMLResponse("")


@router.get("/investments", response_class=HTMLResponse)
def investments_page(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    year: Annotated[int | None, Query()] = None,
    month: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    selected_year = resolve_year(year)
    filter_month = month if month is not None else None
    if filter_month is not None:
        filter_month = _parse_month(str(filter_month))
    context = build_investments_context(
        session, current_user.id, selected_year, selected_month=filter_month
    )
    _page_shell(
        context,
        tab="investments",
        year=selected_year,
        selected_month=resolve_month(filter_month, selected_year),
        filter_month=filter_month,
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/finance_investments.html",
        context=context,
    )


@router.post("/investments", response_class=HTMLResponse)
def create_investment_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    year: Annotated[str, Form()],
    month: Annotated[str, Form()],
    broker: Annotated[str, Form()],
    amount: Annotated[str, Form()],
) -> RedirectResponse:
    parsed_year = _parse_year(year)
    parsed_month = _parse_month(month)
    try:
        parsed_broker = validate_investment_broker(broker.strip())
        upsert_investment_entry(
            session,
            current_user.id,
            parsed_year,
            parsed_month,
            parsed_broker,
            _parse_amount(amount, "amount"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=f"/finance/investments?{_finance_query(parsed_year, parsed_month)}",
        status_code=303,
    )


@router.post("/investments/{entry_id}", response_class=HTMLResponse)
def update_investment_entry(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
    month: str = Form(default=""),
    broker: str = Form(default=""),
    amount: str = Form(default=""),
) -> HTMLResponse:
    entry = session.get(FinanceInvestmentEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    parsed_year = entry.year
    parsed_month = entry.month
    parsed_broker = entry.broker

    if month:
        parsed_month = _parse_month(month)
    if broker:
        try:
            parsed_broker = validate_investment_broker(broker.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    parsed_amount = _parse_amount(amount, "amount") if amount else entry.amount

    if parsed_broker != entry.broker or parsed_month != entry.month:
        session.delete(entry)
        session.commit()
        try:
            entry = upsert_investment_entry(
                session,
                current_user.id,
                parsed_year,
                parsed_month,
                parsed_broker,
                parsed_amount,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        if entry is None:
            return HTMLResponse("")
    else:
        try:
            entry = upsert_investment_entry(
                session,
                current_user.id,
                parsed_year,
                parsed_month,
                parsed_broker,
                parsed_amount,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        if entry is None:
            return HTMLResponse("")

    context = build_investments_context(session, current_user.id, parsed_year)
    return templates.TemplateResponse(
        request=request,
        name="partials/finance_investment_row.html",
        context={
            "entry": entry,
            "month_labels": context["month_labels"],
            "investment_brokers": INVESTMENT_BROKERS,
            "show_month_column": context.get("selected_month") is None,
        },
    )


@router.delete("/investments/{entry_id}", response_class=HTMLResponse)
def delete_investment_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
) -> HTMLResponse:
    entry = session.get(FinanceInvestmentEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(entry)
    session.commit()
    return HTMLResponse("")


@router.get("/transfers", response_class=HTMLResponse)
def transfers_page(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    year: Annotated[int | None, Query()] = None,
    month: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    selected_year = resolve_year(year)
    filter_month = month if month is not None else None
    if filter_month is not None:
        filter_month = _parse_month(str(filter_month))
    context = build_transfers_context(
        session, current_user.id, selected_year, selected_month=filter_month
    )
    _page_shell(
        context,
        tab="transfers",
        year=selected_year,
        selected_month=resolve_month(None, selected_year),
        filter_month=filter_month,
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/finance_transfers.html",
        context=context,
    )


@router.post("/transfers", response_class=HTMLResponse)
def create_transfer_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    year: Annotated[str, Form()],
    month: Annotated[str, Form()],
    from_account: Annotated[str, Form()],
    to_account: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    transaction_date: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        parsed_from, parsed_to = validate_transfer_accounts(
            from_account.strip(),
            to_account.strip(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    parsed_amount = _parse_amount(amount, "amount")
    if parsed_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Amount must be greater than zero.",
        )

    entry = FinanceTransferEntry(
        user_id=current_user.id,
        year=_parse_year(year),
        month=_parse_month(month),
        from_account=parsed_from,
        to_account=parsed_to,
        amount=parsed_amount,
        description=description.strip(),
        transaction_date=_parse_optional_date(transaction_date),
    )
    session.add(entry)
    session.commit()
    return RedirectResponse(
        url=f"/finance/transfers?{_finance_query(entry.year, entry.month)}",
        status_code=303,
    )


@router.post("/transfers/{entry_id}", response_class=HTMLResponse)
def update_transfer_entry(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
    month: str = Form(default=""),
    from_account: str = Form(default=""),
    to_account: str = Form(default=""),
    amount: str = Form(default=""),
    description: str = Form(default=""),
    transaction_date: str = Form(default=""),
) -> HTMLResponse:
    entry = session.get(FinanceTransferEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    parsed_from = entry.from_account
    parsed_to = entry.to_account
    if from_account:
        parsed_from = from_account.strip()
    if to_account:
        parsed_to = to_account.strip()
    try:
        parsed_from, parsed_to = validate_transfer_accounts(parsed_from, parsed_to)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if month:
        entry.month = _parse_month(month)
    entry.from_account = parsed_from
    entry.to_account = parsed_to
    if description:
        entry.description = description.strip()
    if amount:
        parsed_amount = _parse_amount(amount, "amount")
        if parsed_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Amount must be greater than zero.",
            )
        entry.amount = parsed_amount
    entry.description = description.strip()
    entry.transaction_date = _parse_optional_date(transaction_date)
    entry.updated_at = datetime.utcnow()
    session.add(entry)
    session.commit()
    session.refresh(entry)

    context = build_transfers_context(session, current_user.id, entry.year)
    return templates.TemplateResponse(
        request=request,
        name="partials/finance_transfer_row.html",
        context={
            "entry": entry,
            "month_labels": context["month_labels"],
            "transfer_accounts": TRANSFER_ACCOUNTS,
            "show_month_column": context.get("selected_month") is None,
        },
    )


@router.delete("/transfers/{entry_id}", response_class=HTMLResponse)
def delete_transfer_entry(
    session: SessionDep,
    current_user: CurrentUserDep,
    entry_id: UUID,
) -> HTMLResponse:
    entry = session.get(FinanceTransferEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(entry)
    session.commit()
    return HTMLResponse("")
