from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

from app.models.finance import FinanceExpenseEntry
from app.models.investment import Investment
from app.models.security import SecurityLot
from app.services.finance import (
    MonthAmounts,
    expense_category_slug,
    expense_subcategory_slug,
    effective_expense_amount,
    format_finance_source,
    is_expense_reversal,
)
from app.services.securities import (
    ConsolidatedSecurity,
    PortfolioReturnTotals,
    SecurityReturnSummary,
)


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MonthAmounts):
        return {str(month): to_jsonable(amount) for month, amount in value.months.items()}
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {
            str(key) if not isinstance(key, str) else key: to_jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, FinanceExpenseEntry):
        data = value.model_dump(mode="json")
        data["effective_amount"] = to_jsonable(effective_expense_amount(value))
        data["is_reversal"] = is_expense_reversal(value)
        data["source_label"] = format_finance_source(value.source)
        data["category_slug"] = expense_category_slug(value.category)
        data["subcategory_slug"] = expense_subcategory_slug(value.subcategory)
        return data
    if isinstance(value, SecurityLot):
        data = value.model_dump(mode="json")
        data["cost_basis_usd"] = to_jsonable(value.cost_basis_usd)
        data["cost_basis_brl"] = to_jsonable(value.cost_basis_brl)
        data["current_value"] = to_jsonable(value.current_value)
        return data
    if isinstance(value, Investment):
        data = value.model_dump(mode="json")
        asset_type = getattr(value, "asset_type", None)
        data["asset_type_name"] = getattr(asset_type, "name", None)
        data["source_label"] = format_finance_source(value.source)
        return data
    if isinstance(value, SQLModel):
        return value.model_dump(mode="json")
    if isinstance(value, ConsolidatedSecurity):
        data = _dataclass_dict(value)
        data["pl_pct_usd"] = to_jsonable(value.pl_pct_usd)
        data["pl_pct_brl"] = to_jsonable(value.pl_pct_brl)
        return data
    if isinstance(value, (SecurityReturnSummary, PortfolioReturnTotals)):
        data = _dataclass_dict(value)
        data["unrealized_pl_pct_usd"] = to_jsonable(value.unrealized_pl_pct_usd)
        data["unrealized_pl_pct_brl"] = to_jsonable(value.unrealized_pl_pct_brl)
        data["total_return_pct_usd"] = to_jsonable(value.total_return_pct_usd)
        data["total_return_pct_brl"] = to_jsonable(value.total_return_pct_brl)
        return data
    if is_dataclass(value) and not isinstance(value, type):
        return _dataclass_dict(value)
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    return str(value)


def _dataclass_dict(value: Any) -> dict[str, Any]:
    return {
        field.name: to_jsonable(getattr(value, field.name))
        for field in fields(value)
    }


def json_ok(
    payload: Any,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(to_jsonable(payload), status_code=status_code, headers=headers)
