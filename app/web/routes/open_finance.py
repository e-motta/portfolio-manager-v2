from dataclasses import dataclass
from datetime import date
from uuid import UUID

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
from app.services.connections import (
    connections_summary,
    get_all_connections,
)
from app.services.open_finance_match import (
    both_providers_connected,
    overlapping_institutions,
)
from app.services.pluggy_client import is_pluggy_available
from app.services.pluggy_sync import (
    PluggyImportExpenseRow,
    PluggyImportIncomeRow,
    PluggyImportInvestmentRow,
    add_pluggy_connection,
    build_pluggy_expense_import_rows,
    build_pluggy_income_import_rows,
    build_pluggy_investment_import_rows,
    get_pluggy_connections,
    remove_pluggy_connection,
    update_connection_last_synced,
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


@dataclass
class StashedPluggyExpenseImport:
    user_id: UUID
    rows: list[PluggyImportExpenseRow]


@dataclass
class StashedPluggyIncomeImport:
    user_id: UUID
    rows: list[PluggyImportIncomeRow]


@dataclass
class StashedPluggyInvestmentImport:
    user_id: UUID
    rows: list[PluggyImportInvestmentRow]


_pluggy_expense_stash: dict[str, StashedPluggyExpenseImport] = {}
_pluggy_income_stash: dict[str, StashedPluggyIncomeImport] = {}
_pluggy_investment_stash: dict[str, StashedPluggyInvestmentImport] = {}


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
    if user_has_cumbuca(user, session):
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
def open_finance_page(
    session: SessionDep,
    user: CurrentUserDep,
):
    connections = get_all_connections(session, user.id)
    summary = connections_summary(connections)

    cumbuca_connected = user_has_cumbuca(user, session)
    pluggy_connected = summary["has_pluggy"]
    overlap = overlapping_institutions(connections)
    same_institution_warning = None
    if both_providers_connected(connections):
        if overlap:
            names = ", ".join(name.title() for name in overlap)
            same_institution_warning = (
                f"{names} appears connected via both Cumbuca and Pluggy. "
                "Likely duplicate transactions are left unselected at preview."
            )
        else:
            same_institution_warning = (
                "Cumbuca and Pluggy are both connected. Transactions from the "
                "same bank may appear twice — likely duplicates are left unselected."
            )

    return json_ok(
        {
            "connected": cumbuca_connected,
            "cumbuca_connected": cumbuca_connected,
            "pluggy_connected": pluggy_connected,
            "connected_at": user.cumbuca_connected_at if cumbuca_connected else None,
            "pluggy_available": is_pluggy_available(),
            "same_institution_warning": same_institution_warning,
            **summary,
        }
    )


@router.get("/partials/tools")
def open_finance_tools_partial(
    session: SessionDep,
    user: CurrentUserDep,
):
    if not user_has_cumbuca(user, session):
        raise HTTPException(status_code=400, detail="Connect Open Finance first.")

    return json_ok(_open_finance_tools_context(session, user))


@router.post("/disconnect")
def disconnect_open_finance(
    request: Request,
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
    if not user_has_cumbuca(user, session):
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
        import_token = stash_finance_import(user.id, rows)
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
            "preview_kind": "account_debits" if allow_transfer_import else "credit_card",
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
    rows = pop_stashed_finance_import(import_token, user.id)
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
    rows = pop_stashed_finance_import(import_token, user.id)
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
    if not user_has_cumbuca(user, session):
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
        import_token = stash_income_import(user.id, rows)
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
            "import_title": "Review account credits",
            "import_subtitle": (
                f"Credits default to {month_label} {resolved_year}. "
                "Import as income or an investment contribution."
            ),
            "month_labels": MONTH_LABELS,
            "year_options": _preview_year_options(resolved_year, rows),
            "default_import_year": resolved_year,
            "default_import_month": resolved_month,
            "default_import_label": f"{month_label} {resolved_year}",
            "investment_brokers": INVESTMENT_BROKERS,
            "preview_kind": "account_credits",
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
    rows = pop_stashed_income_import(import_token, user.id)
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
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
):
    if not user_has_cumbuca(user, session):
        raise HTTPException(status_code=400, detail="Connect Open Finance first.")

    error = None
    rows = []
    import_token = ""

    try:
        access_token = get_access_token_for_user(session, user)
        rows = build_investment_import_rows(session, access_token=access_token, user_id=user.id)
        import_token = stash_investment_import(user.id, rows)
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
            "confirm_action": "/api/open-finance/sync/investments/confirm",
            "import_title": "Review investment sync",
            "import_subtitle": (
                "Non-exchange positions only · updates existing matches by external ID"
            ),
            "preview_kind": "investments",
        }
    )


@router.post("/sync/investments/confirm")
def confirm_investment_sync(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    import_token: str = Form(...),
    selected_rows: list[str] = Form(default=[]),
) -> RedirectResponse:
    rows = pop_stashed_investment_import(import_token, user.id)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    created, updated = import_selected_investments(
        session, rows, set(selected_rows), user_id=user.id
    )
    return RedirectResponse(
        url=f"/portfolio/investments?imported={created}&updated={updated}",
        status_code=303,
    )


# --- Pluggy Connections ---


@router.get("/connections")
def list_connections(
    session: SessionDep,
    user: CurrentUserDep,
):
    """List all Open Finance connections for the current user."""
    connections = get_all_connections(session, user.id)
    return json_ok(connections_summary(connections))


@router.post("/pluggy/connections")
def add_pluggy_connection_endpoint(
    session: SessionDep,
    user: CurrentUserDep,
    item_id: str = Form(...),
):
    """Add a Pluggy connection by item ID.

    The user obtains the item ID from the Meu Pluggy dashboard after connecting
    their bank. This endpoint validates the item ID and stores the connection.
    """
    from uuid import UUID as UUIDType

    if not is_pluggy_available():
        raise HTTPException(status_code=503, detail="Pluggy is not configured.")

    item_id = item_id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="Item ID is required.")

    try:
        UUIDType(item_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Item ID must be a valid UUID.")

    connection, error = add_pluggy_connection(session, user.id, item_id)
    if error:
        raise HTTPException(status_code=400, detail=error)

    return json_ok({
        "connection": {
            "id": str(connection.id),
            "provider": connection.provider,
            "external_id": connection.external_id,
            "institution_name": connection.institution_name,
            "status": connection.status,
        },
        "message": f"Connected to {connection.institution_name}",
    })


@router.delete("/pluggy/connections/{connection_id}")
def remove_pluggy_connection_endpoint(
    session: SessionDep,
    user: CurrentUserDep,
    connection_id: UUID,
):
    """Remove a Pluggy connection."""
    removed = remove_pluggy_connection(session, user.id, connection_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Connection not found.")
    return json_ok({"removed": True})


@router.get("/pluggy/status")
def pluggy_status(
    session: SessionDep,
    user: CurrentUserDep,
):
    """Get Pluggy integration status."""
    connections = get_pluggy_connections(session, user.id)

    return json_ok({
        "available": is_pluggy_available(),
        "connections": [
            {
                "id": str(conn.id),
                "external_id": conn.external_id,
                "institution_name": conn.institution_name,
                "status": conn.status,
                "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
            }
            for conn in connections
        ],
        "connection_count": len(connections),
    })


def _pluggy_connections_for_preview(
    session,
    user_id: UUID,
    connection_id: str | None = None,
):
    connections = get_pluggy_connections(session, user_id)
    if connection_id:
        try:
            wanted = UUID(str(connection_id).strip())
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid connection ID.") from exc
        connections = [conn for conn in connections if conn.id == wanted]
        if not connections:
            raise HTTPException(status_code=404, detail="Connection not found.")
    if not connections:
        raise HTTPException(status_code=400, detail="No Pluggy connections. Add one first.")
    return connections


# --- Pluggy Sync Endpoints ---


def _stash_pluggy_expense_import(user_id: UUID, rows: list[PluggyImportExpenseRow]) -> str:
    from uuid import uuid4
    token = str(uuid4())
    _pluggy_expense_stash[token] = StashedPluggyExpenseImport(user_id=user_id, rows=rows)
    return token


def _pop_pluggy_expense_import(token: str, user_id: UUID) -> list[PluggyImportExpenseRow] | None:
    """Pop stashed expense import, verifying user ownership."""
    stashed = _pluggy_expense_stash.pop(token, None)
    if stashed is None:
        return None
    if stashed.user_id != user_id:
        return None
    return stashed.rows


def _stash_pluggy_income_import(user_id: UUID, rows: list[PluggyImportIncomeRow]) -> str:
    from uuid import uuid4
    token = str(uuid4())
    _pluggy_income_stash[token] = StashedPluggyIncomeImport(user_id=user_id, rows=rows)
    return token


def _pop_pluggy_income_import(token: str, user_id: UUID) -> list[PluggyImportIncomeRow] | None:
    """Pop stashed income import, verifying user ownership."""
    stashed = _pluggy_income_stash.pop(token, None)
    if stashed is None:
        return None
    if stashed.user_id != user_id:
        return None
    return stashed.rows


def _stash_pluggy_investment_import(user_id: UUID, rows: list[PluggyImportInvestmentRow]) -> str:
    from uuid import uuid4
    token = str(uuid4())
    _pluggy_investment_stash[token] = StashedPluggyInvestmentImport(user_id=user_id, rows=rows)
    return token


def _pop_pluggy_investment_import(token: str, user_id: UUID) -> list[PluggyImportInvestmentRow] | None:
    """Pop stashed investment import, verifying user ownership."""
    stashed = _pluggy_investment_stash.pop(token, None)
    if stashed is None:
        return None
    if stashed.user_id != user_id:
        return None
    return stashed.rows


def _preview_pluggy_expenses(
    session,
    user,
    *,
    year: int,
    month: int,
    connection_id: str | None,
    account_types: set[str] | None,
    import_title: str,
    import_subtitle: str,
    confirm_action: str,
    preview_kind: str,
    allow_transfer_import: bool,
):
    connections = _pluggy_connections_for_preview(session, user.id, connection_id)

    resolved_year = resolve_year(year)
    resolved_month = resolve_month(month, resolved_year)
    month_label = MONTH_LABELS[resolved_month - 1]

    rows, warnings = build_pluggy_expense_import_rows(
        session,
        user.id,
        connections,
        year=resolved_year,
        month=resolved_month,
        account_types=account_types,
    )

    import_token = _stash_pluggy_expense_import(user.id, rows)
    new_count = sum(1 for row in rows if not row.already_exists)
    existing_count = sum(1 for row in rows if row.already_exists)

    return json_ok({
        "error": None if rows else ("; ".join(warnings) if warnings else "No transactions found."),
        "warnings": warnings,
        "rows": [_expense_row_to_dict(row) for row in rows],
        "import_token": import_token,
        "year": resolved_year,
        "month": resolved_month,
        "month_label": month_label,
        "new_count": new_count,
        "existing_count": existing_count,
        "confirm_action": confirm_action,
        "import_title": import_title,
        "import_subtitle": import_subtitle.format(month_label=month_label, year=resolved_year),
        "period_label": "Month",
        "expense_mapping": f"Transactions default to {month_label} {resolved_year}.",
        "expense_categories": EXPENSE_CATEGORIES,
        "expense_category_groups": EXPENSE_CATEGORY_GROUPS,
        "bills_subcategories": BILLS_SUBCATEGORIES,
        "bills_category": BILLS_CATEGORY,
        "month_labels": MONTH_LABELS,
        "year_options": _preview_year_options(resolved_year, rows),
        "default_import_year": resolved_year,
        "default_import_month": resolved_month,
        "allow_transfer_import": allow_transfer_import,
        "transfer_accounts": TRANSFER_ACCOUNTS,
        "investment_brokers": INVESTMENT_BROKERS,
        "preview_kind": preview_kind,
        "provider": "pluggy",
    })


@router.post("/pluggy/sync/expenses/preview")
def preview_pluggy_expenses(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    year: int = Form(default=0),
    month: int = Form(default=0),
    connection_id: str = Form(default=""),
):
    """Preview Pluggy account-debit import."""
    return _preview_pluggy_expenses(
        session,
        user,
        year=year,
        month=month,
        connection_id=connection_id or None,
        account_types={"BANK"},
        import_title="Review Pluggy account debits",
        import_subtitle="Account debits from {month_label} {year}",
        confirm_action="/api/open-finance/pluggy/sync/expenses/confirm",
        preview_kind="account_debits",
        allow_transfer_import=True,
    )


@router.post("/pluggy/sync/credit-card/preview")
def preview_pluggy_credit_card(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    year: int = Form(default=0),
    month: int = Form(default=0),
    connection_id: str = Form(default=""),
):
    """Preview Pluggy credit-card purchase import."""
    return _preview_pluggy_expenses(
        session,
        user,
        year=year,
        month=month,
        connection_id=connection_id or None,
        account_types={"CREDIT"},
        import_title="Review Pluggy card purchases",
        import_subtitle="Card purchases from {month_label} {year}",
        confirm_action="/api/open-finance/pluggy/sync/expenses/confirm",
        preview_kind="credit_card",
        allow_transfer_import=False,
    )


def _expense_row_to_dict(row: PluggyImportExpenseRow) -> dict:
    return {
        "row_key": row.row_key,
        "external_id": row.external_id,
        "year": row.year,
        "month": row.month,
        "category": row.category,
        "vendor": row.vendor,
        "payment_account": row.payment_account,
        "amount": float(row.amount),
        "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
        "already_exists": row.already_exists,
        "selected": row.selected,
        "is_reversal": row.is_reversal,
        "subcategory": row.subcategory,
        "import_kind": row.import_kind,
        "to_account": row.to_account,
        "broker": row.broker,
        "description": row.description,
        "likely_duplicate": row.likely_duplicate,
        "is_bill_payment": row.is_bill_payment,
    }


@router.post("/pluggy/sync/expenses/confirm")
async def confirm_pluggy_expenses(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    """Confirm Pluggy expense import."""
    form = await request.form()
    import_token = str(form.get("import_token") or "")
    selected_rows = form.getlist("selected_rows")

    rows = _pop_pluggy_expense_import(import_token, user.id)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    from app.services.cumbuca_sync import (
        ImportExpenseRow,
        import_selected_account_debits as cumbuca_import_debits,
    )
    from app.services.pluggy_sync import PLUGGY_SOURCE

    converted_rows = [
        ImportExpenseRow(
            row_key=row.row_key,
            external_id=row.external_id,
            year=row.year,
            month=row.month,
            category=row.category,
            vendor=row.vendor,
            payment_account=row.payment_account,
            amount=row.amount,
            transaction_date=row.transaction_date,
            already_exists=row.already_exists,
            selected=row.selected,
            is_reversal=row.is_reversal,
            subcategory=row.subcategory,
            import_kind=row.import_kind,
            to_account=row.to_account,
            broker=row.broker,
            description=row.description,
        )
        for row in rows
    ]

    try:
        expense_created, transfer_created, investment_created = cumbuca_import_debits(
            session,
            user.id,
            converted_rows,
            set(selected_rows),
            kind_overrides=_parse_import_kind_overrides(form),
            to_account_overrides=_parse_to_account_overrides(form),
            broker_overrides=_parse_broker_overrides(form),
            category_overrides=_parse_expense_category_overrides(form),
            subcategory_overrides=_parse_expense_subcategory_overrides(form),
            period_overrides=_parse_period_overrides(form),
            description_overrides=_parse_expense_description_overrides(form),
            source=PLUGGY_SOURCE,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    for conn in get_pluggy_connections(session, user.id):
        update_connection_last_synced(session, conn)

    total = expense_created + transfer_created + investment_created
    return RedirectResponse(
        url=f"/finance/expenses?imported={total}&pluggy=1",
        status_code=303,
    )


@router.post("/pluggy/sync/income/preview")
def preview_pluggy_income(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    year: int = Form(default=0),
    month: int = Form(default=0),
    connection_id: str = Form(default=""),
):
    """Preview Pluggy income import."""
    connections = _pluggy_connections_for_preview(session, user.id, connection_id or None)

    resolved_year = resolve_year(year)
    resolved_month = resolve_month(month, resolved_year)
    month_label = MONTH_LABELS[resolved_month - 1]

    rows, warnings = build_pluggy_income_import_rows(
        session,
        user.id,
        connections,
        year=resolved_year,
        month=resolved_month,
    )

    import_token = _stash_pluggy_income_import(user.id, rows)
    new_count = sum(1 for row in rows if not row.already_exists)
    existing_count = sum(1 for row in rows if row.already_exists)

    return json_ok({
        "error": None if rows else ("; ".join(warnings) if warnings else "No transactions found."),
        "warnings": warnings,
        "rows": [_income_row_to_dict(row) for row in rows],
        "import_token": import_token,
        "year": resolved_year,
        "month": resolved_month,
        "month_label": month_label,
        "new_count": new_count,
        "existing_count": existing_count,
        "confirm_action": "/api/open-finance/pluggy/sync/income/confirm",
        "import_title": "Review Pluggy income",
        "import_subtitle": f"Account credits from {month_label} {resolved_year}",
        "month_labels": MONTH_LABELS,
        "year_options": _preview_year_options(resolved_year, rows),
        "default_import_year": resolved_year,
        "default_import_month": resolved_month,
        "investment_brokers": INVESTMENT_BROKERS,
        "preview_kind": "account_credits",
        "provider": "pluggy",
    })


def _income_row_to_dict(row: PluggyImportIncomeRow) -> dict:
    return {
        "row_key": row.row_key,
        "external_id": row.external_id,
        "year": row.year,
        "month": row.month,
        "description": row.description,
        "amount": float(row.amount),
        "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
        "payment_account": row.payment_account,
        "already_exists": row.already_exists,
        "selected": row.selected,
        "import_kind": row.import_kind,
        "broker": row.broker,
        "likely_duplicate": row.likely_duplicate,
    }


@router.post("/pluggy/sync/income/confirm")
async def confirm_pluggy_income(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    """Confirm Pluggy income import."""
    form = await request.form()
    import_token = str(form.get("import_token") or "")
    selected_rows = form.getlist("selected_rows")

    rows = _pop_pluggy_income_import(import_token, user.id)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    from app.services.cumbuca_sync import (
        ImportIncomeRow,
        import_selected_account_credits as cumbuca_import_credits,
    )
    from app.services.pluggy_sync import PLUGGY_SOURCE

    converted_rows = [
        ImportIncomeRow(
            row_key=row.row_key,
            external_id=row.external_id,
            year=row.year,
            month=row.month,
            description=row.description,
            amount=row.amount,
            transaction_date=row.transaction_date,
            payment_account=row.payment_account,
            already_exists=row.already_exists,
            selected=row.selected,
            import_kind=row.import_kind,
            broker=row.broker,
        )
        for row in rows
    ]

    try:
        income_created, investment_created = cumbuca_import_credits(
            session,
            user.id,
            converted_rows,
            set(selected_rows),
            kind_overrides=_parse_credit_import_kind_overrides(form),
            broker_overrides=_parse_broker_overrides(form),
            period_overrides=_parse_period_overrides(form),
            source=PLUGGY_SOURCE,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    for conn in get_pluggy_connections(session, user.id):
        update_connection_last_synced(session, conn)

    total = income_created + investment_created
    return RedirectResponse(
        url=f"/finance/income?imported={total}&pluggy=1",
        status_code=303,
    )


@router.post("/pluggy/sync/investments/preview")
def preview_pluggy_investments(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    connection_id: str = Form(default=""),
):
    """Preview Pluggy investment import."""
    connections = _pluggy_connections_for_preview(session, user.id, connection_id or None)

    rows, warnings = build_pluggy_investment_import_rows(session, user.id, connections)

    import_token = _stash_pluggy_investment_import(user.id, rows)
    new_count = sum(1 for row in rows if not row.already_exists)
    update_count = sum(1 for row in rows if row.is_update)

    return json_ok({
        "error": None if rows else ("; ".join(warnings) if warnings else "No investments found."),
        "warnings": warnings,
        "rows": [_investment_row_to_dict(row) for row in rows],
        "import_token": import_token,
        "new_count": new_count,
        "update_count": update_count,
        "confirm_action": "/api/open-finance/pluggy/sync/investments/confirm",
        "import_title": "Review Pluggy investments",
        "import_subtitle": "Non-exchange positions only · updates existing matches by external ID",
        "preview_kind": "investments",
        "provider": "pluggy",
    })


def _investment_row_to_dict(row: PluggyImportInvestmentRow) -> dict:
    return {
        "row_key": row.row_key,
        "external_id": row.external_id,
        "institution": row.institution,
        "name": row.name,
        "asset_type_slug": row.asset_type_slug,
        "current_value": float(row.current_value),
        "already_exists": row.already_exists,
        "selected": row.selected,
        "is_update": row.is_update,
    }


@router.post("/pluggy/sync/investments/confirm")
def confirm_pluggy_investments(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    import_token: str = Form(...),
    selected_rows: list[str] = Form(default=[]),
) -> RedirectResponse:
    """Confirm Pluggy investment import."""
    rows = _pop_pluggy_investment_import(import_token, user.id)
    if rows is None:
        raise HTTPException(status_code=400, detail="Import preview expired.")

    from app.services.cumbuca_sync import (
        ImportInvestmentRow,
        import_selected_investments as cumbuca_import_investments,
    )
    from app.services.pluggy_sync import PLUGGY_SOURCE

    converted_rows = [
        ImportInvestmentRow(
            row_key=row.row_key,
            external_id=row.external_id,
            institution=row.institution,
            name=row.name,
            asset_type_slug=row.asset_type_slug,
            current_value=row.current_value,
            already_exists=row.already_exists,
            selected=row.selected,
            is_update=row.is_update,
        )
        for row in rows
    ]

    created, updated = cumbuca_import_investments(
        session, converted_rows, set(selected_rows), source=PLUGGY_SOURCE, user_id=user.id
    )

    for conn in get_pluggy_connections(session, user.id):
        update_connection_last_synced(session, conn)

    return RedirectResponse(
        url=f"/portfolio/investments?imported={created}&updated={updated}&pluggy=1",
        status_code=303,
    )
