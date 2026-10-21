# TradeJournal AI

Automated trading journal that imports closed trading history from MetaTrader 5 (and MetaTrader 4
via an EA bridge) and turns it into tested performance analytics: KPI dashboard, equity/drawdown
curves, timezone-aware P/L calendar, pair/session/setup breakdowns, and structured weekly reviews.

This is an analytical tool only. It never places, modifies, or closes orders.

## Status

TASK-001 to TASK-010 implemented: MT5 collector, MT4 EA, CSV import, simulated demo data,
deal→position reconciliation, tested analytics engine, dashboard, calendar, journal, pair/strategy
analytics, weekly reviews, authentication and security hardening.

```bash
uv sync
uv run uvicorn app.main:create_app --factory --port 8000   # http://127.0.0.1:8000
# Accounts & Sync → "Load SIMULATED demo account" to explore without a broker.
```

## Documentation

| Doc | Content |
| --- | --- |
| [architecture.md](docs/architecture.md) | Components, FastAPI/FastHTML integration, key decisions |
| [requirements.md](docs/requirements.md) | Scope, assumptions, task breakdown, acceptance criteria |
| [database-schema.md](docs/database-schema.md) | Entities, constraints, indexes, idempotency |
| [metatrader-integration.md](docs/metatrader-integration.md) | MT5/MT4 options, limitations, sync design |
| [analytics-definitions.md](docs/analytics-definitions.md) | Metric formulas, edge cases, limitations |

| [setup-guide.md](docs/setup-guide.md) | Local and Docker setup, authentication |
| [api-reference.md](docs/api-reference.md) | REST endpoints (live OpenAPI at `/api/docs`) |
| [testing-guide.md](docs/testing-guide.md) | Test layout and how to run checks |
| [deployment-guide.md](docs/deployment-guide.md) | Production deployment, security, backups |

## Prerequisites (first prototype)

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- SQLite (bundled with Python) for local use; Docker + Docker Compose for PostgreSQL
- For live MT5 import: Windows (PC or VPS) running the MT5 desktop terminal, logged in to the account
- For MT4 import: MT4 terminal with permission to attach an Expert Advisor

## Checks

```bash
uv run ruff check .
uv run pytest
```
