# Testing Guide

```bash
uv run ruff check .
uv run pytest            # ~100 tests, ~10 s, SQLite temp DB per test
uv run pytest tests/unit/test_metrics.py -q
```

| Area | Tests |
| --- | --- |
| Metrics & pips (no wins/losses, breakevens, costs, drawdown, R, pips FX/JPY/gold, missing SL/TP) | `tests/unit/test_metrics.py` |
| Sessions / timezones / DST | `tests/unit/test_sessions.py`, `tests/unit/test_calendar.py` |
| MT5/MT4/CSV normalization, mock determinism, offsets | `tests/unit/test_integrations.py` |
| Collector (read-only scan, state, retries) | `tests/unit/test_collector.py` |
| Ingest API, idempotency, auth, payload limits | `tests/integration/test_ingest_api.py` |
| Positions: partials, scale-in, netting, retry, reconciliation | `tests/integration/test_positions.py` |
| Analytics API, filters, validation | `tests/integration/test_analytics_api.py` |
| Journal, annotations, pagination, CSV export | `tests/integration/test_journal.py` |
| Weekly review, LLM privacy (mocked) | `tests/integration/test_review.py` |
| Security: auth, login rate limit, cross-site blocking, headers, ingest rate limit | `tests/integration/test_security.py` |
| UI smoke tests | `tests/integration/test_*_ui.py` |

Tests never contact a broker or an LLM provider; the MT5 package is faked and LLM calls use
`httpx.MockTransport`.
