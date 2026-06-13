from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import CurrentUserDep
from app.core.db import SessionDep
from app.models.finance import FinanceExpenseEntry, FinanceIncomeEntry
from app.services.finance import (
    EXPENSE_CATEGORIES,
    MAX_EXPENSE_INSTALLMENTS,
    PAYMENT_ACCOUNTS,
    build_expenses_context,
    build_income_context,
    build_summary_context,
    create_expense_entries,
    normalize_summary_amount,
    resolve_month,
    resolve_year,
    upsert_summary_amount,
)
from app.web.dependencies import TemplatesDep, is_htmx

router = APIRouter(prefix="/finance", tags=["finance"])


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


def _summary_line_context(
    session: SessionDep,
    user_id: UUID,
    year: int,
    month: int,
    line_key: str,
    amount: Decimal,
) -> dict | None:
    context = build_summary_context(session, user_id, year, selected_month=month)
    for section in context["summary_sections"]:
        for row in section["rows"]:
            if row.key == line_key:
                return {
                    "row": row,
                    "value": amount,
                    "year": year,
                    "selected_month": month,
                }
    return None


@router.post("/summary/cell", response_model=None)
def update_summary_cell(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    current_user: CurrentUserDep,
    year: Annotated[str, Form()],
    month: Annotated[str, Form()],
    line_key: Annotated[str, Form()],
    amount: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    parsed_year = _parse_year(year)
    parsed_month = _parse_month(month)
    line_key = line_key.strip()
    parsed_amount = normalize_summary_amount(
        line_key, _parse_amount(amount, "amount", allow_negative=True)
    )
    try:
        upsert_summary_amount(
            session,
            current_user.id,
            parsed_year,
            parsed_month,
            line_key,
            parsed_amount,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    line_context = _summary_line_context(
        session,
        current_user.id,
        parsed_year,
        parsed_month,
        line_key,
        parsed_amount,
    )
    if line_context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if is_htmx(request):
        return templates.TemplateResponse(
            request=request,
            name="partials/finance_summary_line.html",
            context=line_context,
        )

    return RedirectResponse(
        url=f"/finance/summary?{_finance_query(parsed_year, parsed_month)}",
        status_code=303,
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
) -> RedirectResponse:
    entry = FinanceIncomeEntry(
        user_id=current_user.id,
        year=_parse_year(year),
        month=_parse_month(month),
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
    description: str = Form(default=""),
    amount: str = Form(default=""),
) -> HTMLResponse:
    entry = session.get(FinanceIncomeEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if month:
        entry.month = _parse_month(month)
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
    installments: Annotated[str, Form()] = "",
    installments_enabled: Annotated[str, Form()] = "",
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

    try:
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
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

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
    entry.updated_at = datetime.utcnow()
    session.add(entry)
    session.commit()
    session.refresh(entry)

    context = build_expenses_context(session, current_user.id, entry.year)
    return templates.TemplateResponse(
        request=request,
        name="partials/finance_expense_row.html",
        context={
            "entry": entry,
            "month_labels": context["month_labels"],
            "expense_categories": EXPENSE_CATEGORIES,
            "payment_accounts": PAYMENT_ACCOUNTS,
        },
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
