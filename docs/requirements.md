# Requirements, Assumptions, and Task Plan

## Scope (first usable release)

Import closed history (MT5 first, MT4 via EA bridge, CSV fallback), store it without duplicates,
reconcile partial closes, and provide: KPI dashboard with filters, equity/drawdown and P/L charts,
timezone-aware calendar, pair/session/setup analytics, trade journal with annotations, weekly review.

Out of scope: placing/modifying/closing orders, open-position (floating P/L) analytics, automatic
setup detection, currency conversion across accounts (accounts are analysed per currency).

## Assumptions (defaults until confirmed)

| # | Assumption | Default |
| - | --- | --- |
| A1 | Platform priority | MT5 first; MT4 bridge after MT5 sync is stable |
| A2 | Terminal host | Windows PC/VPS runs the terminal + collector |
| A3 | Web host | Same machine or LAN, `127.0.0.1` bind; single user |
| A4 | Account type | MT5 hedging accounts fully supported; netting supported incl. reversals |
| A5 | Display timezone | `Asia/Jakarta`; week Monday–Sunday |
| A6 | Broker server offset | Configured per account (common: UTC+2 winter / UTC+3 summer); auto-detect attempted |
| A7 | Sessions | Asia 00:00–09:00 Asia/Tokyo, London 08:00–17:00 Europe/London, New York 08:00–17:00 America/New_York; assigned by entry time, configurable |
| A8 | Pip size | FX 5/3-digit: 10 × point; 4/2-digit: point; metals/indices/CFDs: per-symbol override (XAUUSD default 0.10) |
| A9 | Data | Mock adapter + clearly labelled simulated dataset until real data is available |

## Task breakdown and acceptance criteria

**TASK-001 Discovery & architecture** (this task)
- Docs: architecture, requirements, schema, MT integration, analytics definitions.
- Skeleton package layout, `pyproject.toml`, `.env.example`; `uv sync` and `ruff check` pass.

**TASK-002 Backend foundation**
- Settings via `pydantic-settings`; FastAPI app with FastHTML mounted at `/`.
- SQLAlchemy models + first Alembic migration for all entities; `alembic upgrade head` works on SQLite and PostgreSQL.
- `GET /api/v1/health` returns DB status; pytest + coverage configured; Dockerfile + compose (app + postgres) start.

**TASK-003 MetaTrader integration**
- `BrokerAdapter` protocol; mock adapter with labelled simulated data; CSV adapter.
- Windows MT5 collector: connect, verify terminal/account, read account info, symbols, deals, orders for a date range; push to ingest API.
- Ingest endpoint with per-account token auth. Credentials never logged.
- MT4 MQL4 EA spec + implementation exporting history (WebRequest or CSV).

**TASK-004 Normalization & sync**
- Deals → positions reconciliation including partial closes, scale-ins, netting reversals, MT4 `from #` chains.
- Re-importing the same batch creates zero new rows (tested).
- Incremental sync with overlap window; `sync_run` records status/errors; failed runs retryable.
- Reconciliation check: Σ position net P/L == Σ deal P/L per account.

**TASK-005 Analytics engine**
- All metrics in `analytics-definitions.md` implemented as pure functions with deterministic fixtures and hand-computed expected values, incl. edge cases (no wins, no losses, breakeven, costs, partial closes, currencies, pips, missing SL/TP, timezone boundaries).

**TASK-006 Dashboard**
- KPI cards, filters (account, symbol, date range, direction, setup, session), equity/drawdown, P/L by day/week/month, distributions; every widget updates via HTMX from the analytics service; empty states.

**TASK-007 Calendar**
- Month grid in display TZ; daily net P/L, counts, W/L, colour state; prev/next; day drill-down → trade detail; account/symbol filters.

**TASK-008 Pair & strategy analytics**
- Per-symbol table with all listed metrics; annotation form (setup, timeframes, session, condition, rule adherence, mistakes, ICT tags); breakdowns by annotation fields.

**TASK-009 Weekly review**
- Configurable week start/TZ; sections A–E; previous-week comparison; editable reflection persisted; rule-based summary; optional opt-in LLM narrative.

**TASK-010 Security, testing, deployment**
- Login for non-local binds, CSRF on forms, rate limit on ingest, structured logs without identifiers; compiled Tailwind; full test suite green; setup/deployment/backup docs; end-to-end run with real data if available.

## Definition of done
As listed in the project brief §17.
