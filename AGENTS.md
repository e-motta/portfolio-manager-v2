# Portfolio Manager v2 — Agent Guide

## Overview

Single-portfolio FastAPI + HTMX app for asset-type and exchange-traded security allocation suggestions.

## Commands

```bash
uv sync --extra dev
alembic upgrade head
fastapi dev
pytest
ruff check app
```

## Architecture

- **Routes** (`app/web/routes/`): thin handlers; return HTML or partials only
- **Services** (`app/services/`): allocation and price logic; no HTTP imports
- **Models** (`app/models/`): SQLModel tables
- **Templates** (`app/templates/`): Jinja2; partials under `partials/`

## FastAPI conventions

Follow the [official FastAPI skill](https://github.com/fastapi/fastapi/blob/master/fastapi/.agents/skills/fastapi/SKILL.md):

- Use `Annotated` with `Depends()` type aliases (`SessionDep`, `TemplatesDep`)
- Use sync `def` route handlers for SQLModel DB access
- Put router `prefix`/`tags` on `APIRouter`, not `include_router`
- Declare return types on endpoints where applicable
- Entrypoint: `[tool.fastapi] entrypoint = "app.main:app"`

## HTMX conventions

- HTMX 2.0.7 from CDN in `base.html`
- POST/PUT actions return partial HTML; use `hx-swap="outerHTML"` for row updates
- Suggestion panels swap `#suggestions-panel` via `hx-get` on mode/cash change
- Always auto-escape Jinja output (`{{ var }}`, never `| safe` for user data)
- One swap target per action

## Allocation semantics

- **Type level**: targets sum to 100% of total portfolio
- **Security level**: targets sum to 100% of exchange-traded bucket only
- **`buy_only`**: delta = max(ideal - current, 0); scale buys if sum > new_cash
- **`buy_and_sell`**: delta = ideal - current (negative = sell)

## Do not

- Add auth or multi-user features without explicit request
- Put business logic in route handlers or templates
- Use `ORJSONResponse` or Pydantic `RootModel`
