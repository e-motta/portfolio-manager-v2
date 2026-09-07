# Portfolio Manager v2 — Agent Guide

## Overview

Single-portfolio FastAPI + React app for asset-type and exchange-traded security allocation suggestions.

## Commands

```bash
uv sync --extra dev
cd frontend && npm install && npm run build
alembic upgrade head
fastapi dev
pytest
ruff check app
```

During UI development, run the Vite proxy separately:

```bash
cd frontend && npm run dev   # http://127.0.0.1:5173
fastapi dev                  # http://127.0.0.1:8000
```

## Architecture

- **Routes** (`app/web/routes/`): thin handlers; return JSON under `/api`, or 303 redirects to SPA paths
- **Services** (`app/services/`): allocation, prices, finance, Open Finance, backups; no HTTP imports
- **Models** (`app/models/`): SQLModel tables
- **Frontend** (`frontend/`): Vite + React 19 + TypeScript; React Query for server state, React Router for pages

## FastAPI conventions

Follow the [official FastAPI skill](https://github.com/fastapi/fastapi/blob/master/fastapi/.agents/skills/fastapi/SKILL.md):

- Use `Annotated` with `Depends()` type aliases (`SessionDep`, `CurrentUserDep`)
- Use sync `def` route handlers for SQLModel DB access
- Put router `prefix`/`tags` on `APIRouter`, not `include_router`
- Declare return types on endpoints where applicable
- Serve the built SPA with `app.frontend("/", directory="frontend/dist", fallback="index.html")`
- Entrypoint: `[tool.fastapi] entrypoint = "app.main:app"`
- JSON helpers: `json_ok()` / `to_jsonable()` in `app/web/jsonutil.py`

## React conventions

- Keep SPA URLs identical to the previous app (`/`, `/portfolio/holdings`, `/finance/summary`, `/auth/login`, …)
- Call JSON APIs under `/api/...`; OAuth stays at `/auth/google`, `/auth/callback`, `/auth/cumbuca`, `/auth/logout`
- Colocate page components under `frontend/src/pages/`; shared UI in `frontend/src/components/`
- Fetch with React Query; do not duplicate server state in ad-hoc global stores
- Mutations send `FormData` to match existing FastAPI `Form()` endpoints
- Always treat API payloads as untrusted data and render as text, never as HTML
- Prefer one React Query key per screen; invalidate that key after mutations

## Allocation semantics

- **Type level**: targets sum to 100% of total portfolio
- **Security level**: targets sum to 100% of exchange-traded bucket only
- **`buy_only`**: delta = max(ideal - current, 0); scale buys if sum > new_cash
- **`buy_and_sell`**: delta = ideal - current (negative = sell)

## Auth

- Google OAuth via `/auth/google`; session cookie stores `user_id`
- Login UI is the React route `/auth/login`; `GET /api/auth/config` is public
- Env: `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (see `.env.example`)
- First login creates an empty portfolio with default asset types via `ensure_user_portfolio`
- `bind_current_user` sets `session.info["user_id"]` for scoped queries
- Unauthenticated `/api/*` returns JSON 401; other unauthenticated paths redirect to `/auth/login`

## Do not
- Put business logic in route handlers or React components (keep calculations in `app/services/`)
- Use `ORJSONResponse` or Pydantic `RootModel`
- Serve Jinja/HTMX templates
