from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.auth import CurrentUserDep
from app.core.db import SessionDep
from app.services.cumbuca_oauth import (
    disconnect_cumbuca,
    user_has_cumbuca,
)
from app.services.cumbuca_sync import (
    build_account_credit_import_rows,
    build_account_expense_import_rows,
    build_credit_card_expense_import_rows,
    build_investment_import_rows,
    fetch_open_finance_error,
    get_access_token_for_user,
    import_selected_account_credits,
    import_selected_account_debits,
    import_selected_expenses,
    import_selected_investments,
    pop_stashed_finance_import,
    pop_stashed_income_import,
    pop_stashed_investment_import,
    stash_finance_import,
    stash_income_import,
    stash_investment_import,
)
from app.services.finance import (
    BILLS_CATEGORY,
    BILLS_SUBCATEGORIES,
    EXPENSE_CATEGORIES,
    EXPENSE_CATEGORY_GROUPS,
    INVESTMENT_BROKERS,
    MONTH_LABELS,
    TRANSFER_ACCOUNTS,
    resolve_month,
    resolve_year,
)
from app.web.jsonutil import json_ok

router = APIRouter(prefix="/open-finance", tags=["open-finance"])

_INVESTMENT_TOOL_NAMES = {"list_investments", "openfinance_list_investments"}
_CREDIT_CARD_TOOL_NAMES = {"list_credit_card_bill_transactions"}
_ACCOUNT_TOOL_NAMES = {"list_account_transactions"}


def _year_options(current_year: int) -> list[int]:
    return list(range(current_year - 2, current_year + 3))


def _preview_year_options(import_year: int, rows) -> list[int]:
    years = {import_year}
    for row in rows:
        years.add(row.year)
    low = min(years) - 1
    high = max(years) + 1
    return list(range(low, high + 1))


def _has_any_tool(tool_names: list[str], candidates: set[str]) -> bool:
    return bool(set(tool_names) & candidates)


def _cc_expense_period(year: int, month: int) -> tuple[int, int, str]:
    return year, month, MONTH_LABELS[month - 1]


def _open_finance_tools_context(session, user) -> dict:
    tool_names: list[str] = []
    tools_error = None
    if user_has_cumbuca(user):
        try:
            access_token = get_access_token_for_user(session, user)
            from app.services.cumbuca_mcp import list_tool_names

            tool_names = list_tool_names(access_token)
        except HTTPException as exc:
            tools_error = exc.detail
        except Exception as exc:
            tools_error = fetch_open_finance_error(exc)

    today = date.today()
    return {
        "tool_names": tool_names,
        "tools_error": tools_error,
        "has_credit_card_tools": _has_any_tool(tool_names, _CREDIT_CARD_TOOL_NAMES),
        "has_account_tools": _has_any_tool(tool_names, _ACCOUNT_TOOL_NAMES),
        "has_investment_tools": _has_any_tool(tool_names, _INVESTMENT_TOOL_NAMES),
        "default_year": today.year,
        "default_month": today.month,
        "month_labels": MONTH_LABELS,
        "year_options": _year_options(today.year),
    }


@router.get("")
def open_finance_page(user: CurrentUserDep):
    return json_ok(
        {
            "connected": user_has_cumbuca(user),
            "connected_at": user.cumbuca_connected_at,
        }
    )


@router.get("/partials/tools")
def open_finance_tools_partial(
    session: SessionDep,
    user: CurrentUserDep,
):
    if not user_has_cumbuca(user):
        raise HTTPException(status_code=400, detail="Connect Open Finance first.")

    return json_ok(_open_finance_tools_context(session, user))


@router.post("/disconnect")
def disconnect_open_finance(
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    disconnect_cumbuca(session, user)
    return RedirectResponse(url="/open-finance?disconnected=1", status_code=303)


def _preview_expense_import(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    *,
    builder,
    import_title: str,
    import_subtitle: str,
    period_label: str,
    expense_mapping: str | None,
    year: int,
    month: int,
    default_import_year: int | None = None,
    default_import_month: int | None = None,
    allow_transfer_import: bool = False,
):
    if not user_has_cumbuca(user):
        raise HTTPException(status_code=400, detail="Connect Open Finance first.")

    resolved_year = resolve_year(year)
    resolved_month = resolve_month(month, resolved_year)
    error = None
    rows = []
    warnings: list[str] = []
    import_token = ""

    try:
        access_token = get_access_token_for_user(session, user)
        rows, warnings = builder(
            session,
            user,
            year=resolved_year,
            month=resolved_month,
            access_token=access_token,
        )
        import_token = stash_finance_import(rows)
        if not rows and warnings:
            error = "; ".join(warnings)
    except HTTPException as exc:
        error = exc.detail
    except Exception as exc:
        error = fetch_open_finance_error(exc)

    new_count = sum(1 for row in rows if not row.already_exists)
    existing_count = sum(1 for row in rows if row.already_exists)
    resolved_default_year = default_import_year if default_import_year is not None else resolved_year
    resolved_default_month = (
        default_import_month if default_import_month is not None else resolved_month
    )

    return json_ok(
        {
            "error": error,
            "warnings": warnings,
            "rows": rows,
            "import_token": import_token,
            "year": resolved_year,
            "month": resolved_month,
            "month_label": MONTH_LABELS[resolved_month - 1],
            "new_count": new_count,
            "existing_count": existing_count,
            "import_title": import_title,
            "import_subtitle": import_subtitle,
            "period_label": period_label,
            "expense_mapping": expense_mapping,
            "expense_categories": EXPENSE_CATEGORIES,
            "expense_category_groups": EXPENSE_CATEGORY_GROUPS,
            "bills_subcategories": BILLS_SUBCATEGORIES,
            "bills_category": BILLS_CATEGORY,
            "confirm_action": request.url.path.replace("/preview", "/confirm"),
            "month_labels": MONTH_LABELS,
            "year_options": _preview_year_options(resolved_year, rows),
            "default_import_year": resolved_default_year,
            "default_import_month": resolved_default_month,
            "default_import_label": (
                f"{MONTH_LABELS[resolved_default_month - 1]} {resolved_default_year}"
            ),
            "allow_transfer_import": allow_transfer_import,
            "transfer_accounts": TRANSFER_ACCOUNTS,
            "investment_brokers": INVESTMENT_BROKERS,
        }
    )


@router.post("/sync/credit-card/preview")
def preview_credit_card_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    year: int = Form(default=0),
    month: int = Form(default=0),
):
    resolved_year = resolve_year(year)
    resolved_month = resolve_month(month, resolved_year)
    cc_expense_year, cc_expense_month, cc_expense_month_label = _cc_expense_period(
        resolved_year,
        resolved_month,
    )
    return _preview_expense_import(
        request,
        session,
        user,
        builder=build_credit_card_expense_import_rows,
        import_title="Review credit card charges",
        import_subtitle=f"{MONTH_LABELS[resolved_month - 1]} {resolved_year} statement",
        period_label="Statement",
        expense_mapping=(
            f"Charges default to {cc_expense_month_label} {cc_expense_year}. "
            "Change any row to import elsewhere."
        ),
        year=year,
        month=month,
        default_import_year=cc_expense_year,
        default_import_month=cc_expense_month,
    )


def _parse_expense_category_overrides(form) -> dict[str, str]:
    return {
        key.removeprefix("category_"): value
        for key, value in form.items()
        if key.startswith("category_") and value
    }


def _parse_expense_subcategory_overrides(form) -> dict[str, str | None]:
    return {
        key.removeprefix("subcategory_"): (value or None)
        for key, value in form.items()
        if key.startswith("subcategory_")
    }


def _parse_expense_description_overrides(form) -> dict[str, str]:
    return {
        key.removeprefix("description_"): value
        for key, value in form.items()
        if key.startswith("description_")
    }


def _parse_period_overrides(form) -> dict[str, tuple[int, int]]:
    overrides: dict[str, tuple[int, int]] = {}
    for key, value in form.items():
        if not key.startswith("import_month_") or not value:
            continue
        row_key = key.removeprefix("import_month_")
        year_raw = form.get(f"import_year_{row_key}")
        if year_raw is None:
            continue
        try:
            month = int(value)
            year = int(year_raw)
        except (TypeError, ValueError):
            continue
        if 1 <= month <= 12:
            overrides[row_key] = (year, month)
    return overrides


def _parse_import_kind_overrides(form) -> dict[str, str]:
    return {
        key.removeprefix("import_kind_"): value
        for key, value in form.items()
        if key.startswith("import_kind_") and value in {"expense", "transfer", "investment"}
    }


def _parse_broker_overrides(form) -> dict[str, str]:
    return {
        key.removeprefix("broker_"): value
        for key, value in form.items()
        if key.startswith("broker_") and value
    }


def _parse_credit_import_kind_overrides(form) -> dict[str, str]:
    return {
        key.removeprefix("import_kind_"): value
        for key, value in form.items()
        if key.startswith("import_kind_") and value in {"income", "investment"}
    }


def _parse_to_account_overrides(form) -> dict[str, str]:
    return {
        key.removeprefix("to_account_"): value
        for key, value in form.items()
        if key.startswith("to_account_") and value
    }


async def _confirm_account_debits_import(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    form = await request.form()
    import_token = str(form.get("import_token") or "")
    selected_rows = form.getlist("selected_rows")
    rows = pop_stashed_finance_import(import_token)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    try:
        expense_created, transfer_created, investment_created = import_selected_account_debits(
            session,
            user.id,
            rows,
            set(selected_rows),
            kind_overrides=_parse_import_kind_overrides(form),
            to_account_overrides=_parse_to_account_overrides(form),
            broker_overrides=_parse_broker_overrides(form),
            category_overrides=_parse_expense_category_overrides(form),
            subcategory_overrides=_parse_expense_subcategory_overrides(form),
            period_overrides=_parse_period_overrides(form),
            description_overrides=_parse_expense_description_overrides(form),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if investment_created and not expense_created and not transfer_created:
        url = f"/finance/investments?imported={investment_created}"
    elif transfer_created and not expense_created and not investment_created:
        url = f"/finance/transfers?imported={transfer_created}"
    elif expense_created and not transfer_created and not investment_created:
        url = f"/finance/expenses?imported={expense_created}"
    elif transfer_created or expense_created or investment_created:
        params: list[str] = []
        if expense_created:
            params.append(f"expenses={expense_created}")
        if transfer_created:
            params.append(f"transfers={transfer_created}")
        if investment_created:
            params.append(f"investments={investment_created}")
        base = "/finance/expenses" if expense_created else "/finance/transfers"
        if not expense_created and not transfer_created:
            base = "/finance/investments"
        url = f"{base}?{'&'.join(params)}"
    else:
        url = "/finance/expenses?imported=0"
    return RedirectResponse(url=url, status_code=303)


async def _confirm_expense_import(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    form = await request.form()
    import_token = str(form.get("import_token") or "")
    selected_rows = form.getlist("selected_rows")
    rows = pop_stashed_finance_import(import_token)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        set(selected_rows),
        category_overrides=_parse_expense_category_overrides(form),
        subcategory_overrides=_parse_expense_subcategory_overrides(form),
        period_overrides=_parse_period_overrides(form),
        description_overrides=_parse_expense_description_overrides(form),
    )
    return RedirectResponse(
        url=f"/finance/expenses?imported={created}",
        status_code=303,
    )


@router.post("/sync/credit-card/confirm")
async def confirm_credit_card_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    return await _confirm_expense_import(request, session, user)


@router.post("/sync/account-debits/preview")
def preview_account_debits_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    year: int = Form(default=0),
    month: int = Form(default=0),
):
    resolved_year = resolve_year(year)
    resolved_month = resolve_month(month, resolved_year)
    month_label = MONTH_LABELS[resolved_month - 1]
    return _preview_expense_import(
        request,
        session,
        user,
        builder=build_account_expense_import_rows,
        import_title="Review account debits",
        import_subtitle=f"{month_label} {resolved_year}",
        period_label="Month",
        expense_mapping=(
            f"Debits default to {month_label} {resolved_year}. "
            "All amounts are outflows. Import as expense, transfer, or investment."
        ),
        year=year,
        month=month,
        default_import_year=resolved_year,
        default_import_month=resolved_month,
        allow_transfer_import=True,
    )


@router.post("/sync/account-debits/confirm")
async def confirm_account_debits_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    return await _confirm_account_debits_import(request, session, user)


@router.post("/sync/account-credits/preview")
def preview_account_credits_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    year: int = Form(default=0),
    month: int = Form(default=0),
):
    if not user_has_cumbuca(user):
        raise HTTPException(status_code=400, detail="Connect Open Finance first.")

    resolved_year = resolve_year(year)
    resolved_month = resolve_month(month, resolved_year)
    month_label = MONTH_LABELS[resolved_month - 1]
    error = None
    rows = []
    warnings: list[str] = []
    import_token = ""

    try:
        access_token = get_access_token_for_user(session, user)
        rows, warnings = build_account_credit_import_rows(
            session,
            user,
            year=resolved_year,
            month=resolved_month,
            access_token=access_token,
        )
        import_token = stash_income_import(rows)
        if not rows and warnings:
            error = "; ".join(warnings)
    except HTTPException as exc:
        error = exc.detail
    except Exception as exc:
        error = fetch_open_finance_error(exc)

    new_count = sum(1 for row in rows if not row.already_exists)
    existing_count = sum(1 for row in rows if row.already_exists)

    return json_ok(
        {
            "error": error,
            "warnings": warnings,
            "rows": rows,
            "import_token": import_token,
            "year": resolved_year,
            "month": resolved_month,
            "month_label": month_label,
            "new_count": new_count,
            "existing_count": existing_count,
            "confirm_action": "/api/open-finance/sync/account-credits/confirm",
            "month_labels": MONTH_LABELS,
            "year_options": _preview_year_options(resolved_year, rows),
            "default_import_year": resolved_year,
            "default_import_month": resolved_month,
            "default_import_label": f"{month_label} {resolved_year}",
            "investment_brokers": INVESTMENT_BROKERS,
        }
    )


@router.post("/sync/account-deposits/preview")
def preview_account_deposits_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    year: int = Form(default=0),
    month: int = Form(default=0),
):
    return preview_account_credits_sync(request, session, user, year, month)


@router.post("/sync/account-credits/confirm")
async def confirm_account_credits_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    form = await request.form()
    import_token = str(form.get("import_token") or "")
    selected_rows = form.getlist("selected_rows")
    rows = pop_stashed_income_import(import_token)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    try:
        income_created, investment_created = import_selected_account_credits(
            session,
            user.id,
            rows,
            set(selected_rows),
            kind_overrides=_parse_credit_import_kind_overrides(form),
            broker_overrides=_parse_broker_overrides(form),
            period_overrides=_parse_period_overrides(form),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if investment_created and not income_created:
        url = f"/finance/investments?imported={investment_created}"
    elif income_created and not investment_created:
        url = f"/finance/income?imported={income_created}"
    elif investment_created and income_created:
        url = (
            f"/finance/income?imported={income_created}"
            f"&investments={investment_created}"
        )
    else:
        url = "/finance/income?imported=0"
    return RedirectResponse(url=url, status_code=303)


@router.post("/sync/account-deposits/confirm")
async def confirm_account_deposits_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    return await confirm_account_credits_sync(request, session, user)


@router.post("/sync/investments/preview")
def preview_investment_sync(
    session: SessionDep,
    user: CurrentUserDep,
):
    if not user_has_cumbuca(user):
        raise HTTPException(status_code=400, detail="Connect Open Finance first.")

    error = None
    rows = []
    import_token = ""

    try:
        access_token = get_access_token_for_user(session, user)
        rows = build_investment_import_rows(session, access_token=access_token)
        import_token = stash_investment_import(rows)
    except HTTPException as exc:
        error = exc.detail
    except Exception as exc:
        error = fetch_open_finance_error(exc)

    new_count = sum(1 for row in rows if not row.already_exists)
    update_count = sum(1 for row in rows if row.is_update)

    return json_ok(
        {
            "error": error,
            "rows": rows,
            "import_token": import_token,
            "new_count": new_count,
            "update_count": update_count,
        }
    )


@router.post("/sync/investments/confirm")
def confirm_investment_sync(
    session: SessionDep,
    user: CurrentUserDep,
    import_token: str = Form(...),
    selected_rows: list[str] = Form(default=[]),
) -> RedirectResponse:
    rows = pop_stashed_investment_import(import_token)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    created, updated = import_selected_investments(session, rows, set(selected_rows))
    return RedirectResponse(
        url=f"/portfolio/investments?imported={created}&updated={updated}",
        status_code=303,
    )
