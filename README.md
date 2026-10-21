# TradeJournal AI

Automated trading journal that imports closed trading history from MetaTrader 5 (and MetaTrader 4
via an EA bridge) and turns it into tested performance analytics: KPI dashboard, equity/drawdown
curves, timezone-aware P/L calendar, pair/session/setup breakdowns, and structured weekly reviews.

This is an analytical tool only. It never places, modifies, or closes orders.

## Status

TASK-001 (discovery and architecture) — documentation and project skeleton only. No application
code runs yet. See [docs/requirements.md](docs/requirements.md) for the task plan.

## Documentation

| Doc | Content |
| --- | --- |
| [architecture.md](docs/architecture.md) | Components, FastAPI/FastHTML integration, key decisions |
| [requirements.md](docs/requirements.md) | Scope, assumptions, task breakdown, acceptance criteria |
| [database-schema.md](docs/database-schema.md) | Entities, constraints, indexes, idempotency |
| [metatrader-integration.md](docs/metatrader-integration.md) | MT5/MT4 options, limitations, sync design |
| [analytics-definitions.md](docs/analytics-definitions.md) | Metric formulas, edge cases, limitations |

`api-reference.md`, `setup-guide.md`, `testing-guide.md`, and `deployment-guide.md` are written in
the tasks that introduce the corresponding functionality.

## Prerequisites (first prototype)

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- SQLite (bundled with Python) for local use; Docker + Docker Compose for PostgreSQL
- For live MT5 import: Windows (PC or VPS) running the MT5 desktop terminal, logged in to the account
- For MT4 import: MT4 terminal with permission to attach an Expert Advisor

## Quick check

```bash
uv sync
uv run ruff check .
```
