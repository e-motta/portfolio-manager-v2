from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.web.navigation import NAV_SECTIONS

BASE_DIR = Path(__file__).resolve().parent.parent


def _format_brl(value) -> str:
    amount = f"{Decimal(value):,.2f}"
    return f"R$\u00a0{amount}"


def _format_usd(value) -> str:
    amount = f"{Decimal(value):,.2f}"
    return f"${amount}"


def _format_num(value, places: int = 4) -> str:
    return f"{Decimal(value):.{places}f}"


def _format_action(value: str) -> str:
    labels = {"buy": "Buy", "sell": "Sell", "hold": "Hold"}
    return labels.get(str(value).lower(), str(value))


def _format_date(value) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _format_datetime(value) -> str:
    if not isinstance(value, datetime):
        return str(value)

    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    local = dt.astimezone(ZoneInfo(settings.DISPLAY_TIMEZONE))
    return f"{local.strftime('%d/%m/%Y %H:%M')} {settings.DISPLAY_TIMEZONE_LABEL}"


def _format_signed_usd(value) -> str:
    amount = Decimal(value)
    if amount > 0:
        return f"+${amount:,.2f}"
    return f"${amount:,.2f}"


def _format_signed_brl(value) -> str:
    amount = Decimal(value)
    if amount > 0:
        return f"+R$\u00a0{amount:,.2f}"
    return f"R$\u00a0{amount:,.2f}"


def _format_signed_pct(value) -> str:
    if value is None:
        return "—"
    amount = Decimal(value).quantize(Decimal("0.1"))
    text = f"{amount:.1f}%"
    if amount > 0:
        return f"+{text}"
    return text


def _pl_class(value) -> str:
    if value is None:
        return "pl-neutral"
    amount = Decimal(value)
    if amount > 0:
        return "pl-positive"
    if amount < 0:
        return "pl-negative"
    return "pl-neutral"


def _build_templates() -> Jinja2Templates:
    jinja = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    jinja.env.filters["brl"] = _format_brl
    jinja.env.filters["usd"] = _format_usd
    jinja.env.filters["pl_usd"] = _format_signed_usd
    jinja.env.filters["pl_brl"] = _format_signed_brl
    jinja.env.filters["pl_pct"] = _format_signed_pct
    jinja.env.filters["pl_class"] = _pl_class
    jinja.env.filters["num"] = _format_num
    jinja.env.filters["action_label"] = _format_action
    jinja.env.filters["date_fmt"] = _format_date
    jinja.env.filters["datetime_fmt"] = _format_datetime
    jinja.env.globals["nav_sections"] = NAV_SECTIONS
    return jinja


templates = _build_templates()


def get_templates() -> Jinja2Templates:
    return templates


TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"
