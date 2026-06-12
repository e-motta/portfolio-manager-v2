# Portfolio Manager v2

FastAPI + HTMX portfolio manager for tracking asset-type and exchange-traded security allocations with buy-only and buy-and-sell rebalancing suggestions.

## Setup

```bash
uv sync --extra dev
alembic upgrade head
fastapi dev
```

Open http://127.0.0.1:8000

## Features

- Manage asset types with target percentages (Cash, Bonds, Exchange Traded, etc.)
- Manage exchange-traded securities (stocks, ETFs, REITs) with bucket-scoped targets
- Suggestions at asset-type and security levels
- Buy-only mode (never suggests selling) or buy-and-sell rebalancing mode
- Manual price refresh for exchange-traded securities via yfinance

## Tests

```bash
pytest
ruff check app
```

## Project layout

- `app/services/allocation.py` — rebalancing logic
- `app/web/routes/` — HTMX HTML endpoints
- `app/templates/` — Jinja2 pages and partials
- `AGENTS.md` — AI agent conventions
