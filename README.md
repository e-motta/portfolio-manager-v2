# Portfolio Manager v2

Personal portfolio and finance tracker built with FastAPI and HTMX. One portfolio per user: manage asset-class and security allocation, track Brazilian personal finance, import bank data via Open Finance, and back up everything to Google Drive.

## Setup

```bash
uv sync --extra dev
cp .env.example .env   # fill in OAuth credentials
alembic upgrade head
fastapi dev
```

Open http://127.0.0.1:8000

### Environment

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite database path (default `sqlite:///./local.db`) |
| `SECRET_KEY` | Session cookie signing |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Google sign-in and Drive backups |
| `CUMBUCA_MCP_URL`, `CUMBUCA_AUTH_SERVER`, `CUMBUCA_REDIRECT_URI` | Cumbuca Open Finance bank sync |

External data (no config): Yahoo Finance for quotes and spot USD/BRL; Banco Central Olinda API for PTAX.

## Features

### Portfolio overview

- **Dashboard** — total portfolio value (BRL), allocation sleeve size, overweight/underweight class counts, and a per-class table with market value, allocation bar, current vs target weights, and drift
- **Listed Securities** value is derived automatically from holdings; classes without targets appear as outside allocation

### Securities (exchange-traded)

- Consolidated positions by ticker: quantity, average cost (USD/BRL), last price, market value, weight, editable target weight (must sum to 100% within the sleeve)
- Performance by ticker: unrealized P/L, net dividends, total return (USD/BRL)
- Tax lot history per buy with trade date, FX rate, cost basis, and source (manual or statement import)
- Dividend tracking: gross, withholding, net (USD); add manually or import
- **Add trade** / **Add dividend** modals; inline edit and delete on lots and dividends
- **Refresh prices** via Yahoo Finance; **Update PTAX rates** to replace provisional FX on lots with Banco Central official rates
- Deferred page load with skeleton placeholders while market data is fetched

### Other investments

- Non-exchange-traded positions (cash, bonds, crypto, real estate, custom classes) with institution, name, value
- Summary by bank/institution; add, inline edit, and delete positions
- Link to Open Finance for balance sync

### Asset classes

- Default classes on first login: Cash (5%), Bonds (20%), Listed Securities (60%), Crypto (5%), Real Estate (10%)
- Add custom classes; rename and set/clear target weights inline
- Target total indicator (100% / partial / none); Listed Securities class is protected from deletion

### Rebalancing suggestions

- **By asset class** — suggestions toward type-level targets across the full portfolio
- **By holding** — suggestions within the Listed Securities sleeve only
- **Cash-only** mode — buy-only adjustments; scales buys when cash input is insufficient
- **Full rebalance** mode — includes sells
- Configurable cash to deploy (BRL); shows current/target weights, ideal value, action badge, and adjustment amount

### Finance

Year-scoped personal finance with month pills, year selector, and monthly charts on every tab.

- **Summary** — income, expenses, and balance (month + YTD); monthly chart; breakdown cards for income (PJ / Outros), Bills (paid/unpaid), and day-to-day spending by payment account
- **Income** — PJ and Outros categories; add, edit, delete; period totals and monthly chart
- **Expenses** — 17 categories (Bills, Alimentação, Esporte, Assinaturas, Vida, Outros) with Bills subcategories and effective-amount rules (e.g. shared rent split); payment accounts (Nubank, Nuconta, XP/BB credit and debit, Wise, cash); installments up to 48 months; vendor memory for category autocompletion; reversal linking for refunds; category and payment-account breakdowns; quick-add per section; Manual vs Open Finance source badges
- **Transfers** — move money between accounts with optional description and date
- **Investments (cash flow)** — monthly contributions by broker (XP, IB, Nubank, MB); 30% annual target derived from year income; YTD progress and per-broker breakdown (distinct from portfolio Other investments balances)

### Open Finance (Cumbuca)

- Connect bank via OAuth (read-only); connection status and disconnect
- Preview-before-import on every sync path with row selection and duplicate detection
- **Credit card charges** → expenses
- **Account debits** → expense, transfer, or investment (per row)
- **Account credits** → income or investment (per row)
- **Investment balances** → portfolio Other investments (exchange-traded positions stay in Securities)

### Imports

- **Interactive Brokers statement (CSV)** — preview and selective import of tax lots and dividends from the Securities page
- **Open Finance** — credit card, debits, credits, and investment balances (see above)

### Snapshots and backups

- **Portfolio snapshots** — capture point-in-time state on any date (replaces same-date snapshot); history table and detail view; delete snapshots
- **Google Drive backups** — separate OAuth scope; create, list, restore, and delete JSON backups (portfolio + finance data)

### Authentication and UI

- Google OAuth sign-in; session cookie; sign out; first login creates an empty portfolio with default asset classes
- Sidebar or top navigation layout (persisted in browser)
- HTMX inline editing on tables; modal forms for adds; import dropzone with preview modal

## Tests

```bash
pytest
ruff check app
```

## Project layout

- `app/services/` — allocation, prices, finance, Open Finance sync, backups
- `app/web/routes/` — HTMX HTML endpoints
- `app/models/` — SQLModel tables
- `app/templates/` — Jinja2 pages and partials
- `AGENTS.md` — AI agent conventions
