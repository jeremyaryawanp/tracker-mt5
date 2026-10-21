# Architecture

## Components

```
 Windows PC / VPS                                 Web host (same PC, LAN box, or Docker)
┌─────────────────────────────┐                  ┌──────────────────────────────────────────┐
│ MT5 terminal (logged in)    │                  │ ASGI process (uvicorn)                    │
│   ▲ MetaTrader5 py package  │  HTTPS + token   │  ├─ /api/v1/*  FastAPI  (JSON, ingest)    │
│ MT5 collector (Python)  ────┼─────────────────►│  └─ /*         FastHTML (HTML + HTMX)     │
└─────────────────────────────┘   POST batches   │        │                │                 │
 ┌─────────────────────────────┐                 │        ▼                ▼                 │
 │ MT4 terminal + MQL4 EA  ────┼── WebRequest ──►│   services/  (sync, analytics, reporting) │
 └─────────────────────────────┘   or CSV file   │        ▼                                  │
 CSV / HTML statement upload ─────── UI ────────►│   repositories/ ── SQLAlchemy ── DB       │
                                                 └──────────────────────────────────────────┘
                                                            SQLite (dev) / PostgreSQL (prod)
```

1. **Collectors** (outside the web app): read broker history on the machine where the terminal runs
   and push normalized batches. MT5: Python collector using the official `MetaTrader5` package.
   MT4: MQL4 EA/script. Both are read-only.
2. **Ingest API** (FastAPI): authenticated per-account token, validates batches with Pydantic,
   hands them to the synchronization service.
3. **Synchronization service**: idempotent upsert of raw deals, reconciliation into positions,
   sync-run bookkeeping (status, error, retry).
4. **Analytics service**: single source of truth for every metric. Pure functions over
   position/deal records using `Decimal`; no metric is computed in templates or routes.
5. **Frontend** (FastHTML + HTMX + Tailwind + Plotly.js): server-rendered pages, HTMX partials for
   filters, calendar navigation, and annotation forms.

## FastAPI / FastHTML integration

Decision: **one ASGI process, two route namespaces, one shared service layer.**

- `app/main.py` builds the FastAPI app, registers API routers under `/api/v1`, then mounts the
  FastHTML app at `/`. FastAPI routes are registered first, so `/api/*` never reaches FastHTML;
  FastHTML owns every other path. No path is owned by both.
- FastHTML handlers call `app/services/*` directly (in-process) instead of calling the REST API
  over HTTP. Both API and UI are thin adapters over the same services, which keeps metric logic in
  one place and avoids double serialization.
- The REST API exists for: collector/EA ingest, CSV export, and future clients.
- Auth: session cookie (Starlette `SessionMiddleware`) for UI; bearer ingest tokens for
  collectors. Both resolve to a `user_id` used for account-level data isolation.

Alternative considered: two processes (FastHTML calling FastAPI via `httpx`). Cleaner separation but
adds latency, a second deployable, and duplicated auth. Can be split later because the UI depends
only on the service layer.

## Key decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Python | 3.12 via `uv` | Spec target; SQLAlchemy 2.1 requires ≥3.11 |
| DB | SQLite locally, PostgreSQL in Docker Compose/prod; Alembic migrations | Zero-setup prototype; portable SQLAlchemy types |
| Money | `Numeric(18, 2)` / `Decimal`; never `float` | Exact sums; matches broker statements |
| Prices | `Numeric(20, 10)` | Covers JPY, crypto, index precision |
| Time | Store UTC (`timestamptz`) + raw broker server time + offset used | MT5/MT4 report broker *server* time, not UTC |
| Display TZ | `Asia/Jakarta` default, user-configurable | Spec |
| Source of truth | Raw deals; positions are derived and rebuildable | Partial closes and reconciliation |
| Ingest | Single idempotent pipeline for MT5, MT4, CSV, mock | One code path to test |
| Analytics engine | Pure Python + `Decimal`; pandas only for time-series resampling | Exactness, easy unit tests |
| Charts | Plotly.js (CDN) fed by JSON from the analytics service | Interactive, no build step |
| CSS | Tailwind via CDN for prototype; compiled CSS in TASK-010 | Fast iteration, no Node needed early |
| Background work | None initially; sync is collector-push. Redis/worker only if needed | Avoid unjustified infra |
| Auth | Single admin user + per-account ingest tokens; schema has `user_id` from day 1 | Local single-user default, multi-user ready |
| LLM reviews | Off by default; opt-in, aggregated metrics only | Privacy |

## Layering rules

- `integrations/*` know broker formats; they output `schemas.ingest.*` objects only.
- `services/*` hold business logic; no HTTP or HTML.
- `repositories/*` are the only code that issues SQL.
- `api/routes/*` and `frontend/routes/*` validate input, call services, render output.
- No module in `app/` imports `MetaTrader5`; only `collector/` does.
