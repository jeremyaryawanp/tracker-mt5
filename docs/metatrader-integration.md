# MetaTrader Integration: Options and Limitations

## Facts that drive the design

- The official `MetaTrader5` Python package is published on PyPI with **Windows (`win_amd64`) wheels
  only** (verified on PyPI for 5.0.6231). It talks over IPC to an MT5 desktop terminal running on the
  **same machine**. It does not work with MT4.
- A remote web server cannot reach a user's terminal by itself; a collector next to the terminal
  must push data out.
- MetaTrader timestamps are **broker server time**, not UTC. The offset is broker-specific and
  often follows a DST rule (e.g. UTC+2 winter / UTC+3 summer). It must be configured or detected.
- There is no official MT4 Python API.

## MT5 options

| Option | Feasible | Notes |
| --- | --- | --- |
| A. Python collector + `MetaTrader5` package on Windows | **Yes – chosen** | Official, read-only calls: `initialize`, `terminal_info`, `account_info`, `symbols_get`, `symbol_info`, `history_deals_get`, `history_orders_get`. Terminal must be running and logged in. |
| B. MQL5 EA pushing via `WebRequest` | Yes | No Python on the client; URL must be whitelisted in terminal options. Kept as a fallback. |
| C. Statement/CSV export upload | Yes | Manual; used as universal fallback. |
| D. MT5 on Linux via Wine + Windows Python | Unofficial | Community approach; not supported in first release. |
| E. Broker Manager/Web APIs | No | Requires broker-level access. |

### MT5 collector design
- Config file on the Windows host: ingest URL, ingest token, terminal path (optional), sync interval,
  history start date, overlap window (default 3 days). If login is required, the password is read
  from the OS keyring or prompt — never stored in plaintext, never sent to the web app.
- Steps per run: `initialize()` → check `terminal_info().connected` and `account_info()` →
  fetch `history_deals_get(from, to)` and `history_orders_get(from, to)` → fetch `symbol_info`
  for traded symbols → POST batch → on success store `last_synced_to`; on failure retry with
  exponential backoff and report error to `/api/v1/sync-runs`.
- Never calls `order_send`, `order_check`, or `positions_*` modifications. A unit test asserts the
  collector module does not reference trading functions.
- Logs mask login number and server; no balances in logs.

### MT5 data mapping
- Deal `entry`: `IN`, `OUT`, `INOUT` (netting reversal), `OUT_BY` (close by opposite position).
- Position grouping by `position_id`. Netting `INOUT` deals are split into the closing part of the
  old position and the opening part of the new one.
- Net P/L per deal = `profit + commission + swap + fee` (MT5 reports these as separate signed fields).
- Initial SL/TP: taken from the position's opening order (`history_orders_get` → `sl`, `tp`) when
  non-zero. Later SL/TP modifications are **not** in history, so values are labelled "initial order
  SL/TP". Whether the deal record in the Python API also exposes `sl`/`tp` must be verified on the
  user's terminal build.

## MT4 options

| Option | Feasible | Notes |
| --- | --- | --- |
| A. MQL4 EA/script → `WebRequest` POST to ingest API | **Yes – preferred** | URL must be added under Tools → Options → Expert Advisors. Token in EA input. |
| B. MQL4 EA/script → CSV in `MQL4/Files`, then upload or collector picks it up | Yes | No network permission needed. |
| C. Third-party bridges (ZeroMQ DLLs, etc.) | Possible | Extra DLLs; not chosen. |
| D. MT5 Python package | **No** | Does not support MT4. |

### MT4 limitations
- History visible to MQL4 (`OrdersHistoryTotal`, `OrderSelect(..., MODE_HISTORY)`) is limited to
  what the Account History tab shows; the user must select "All History".
- No deal objects: each closed ticket becomes two synthetic deals (`open`, `close`).
- Partial close: the original ticket closes with the closed volume, a new ticket continues with
  comment `from #<ticket>`. The chain is merged into one position for position-level analytics.
- `OrderStopLoss/OrderTakeProfit` return the **last** SL/TP, not the initial one → labelled
  `LAST_KNOWN`; R-multiple is not computed from it.
- `OrderProfit` excludes commission and swap; net = profit + commission + swap.

## Common normalized schema (ingest batch)

```json
{
  "schema_version": 1,
  "source": "MT5_COLLECTOR",
  "account": {"platform": "MT5", "login_hash": "…", "broker_name": "…", "broker_server": "…",
              "currency": "USD", "account_type": "DEMO", "margin_mode": "HEDGING"},
  "range": {"from": "2026-01-01T00:00:00Z", "to": "2026-10-21T00:00:00Z"},
  "server_utc_offset_minutes": 180,
  "symbols": [{"symbol": "XAUUSD", "digits": 2, "point": "0.01", "contract_size": "100", "...": "..."}],
  "deals":   [{"external_deal_id": "123", "external_order_id": "456", "external_position_id": "456",
               "symbol": "XAUUSD", "deal_type": "BUY", "entry": "IN", "time_server": "…",
               "price": "2350.12", "volume": "0.10", "profit": "0.00", "commission": "-0.70",
               "swap": "0.00", "fee": "0.00", "sl": null, "tp": null, "magic": 0, "comment": ""}],
  "orders":  [{"external_order_id": "456", "external_position_id": "456", "sl": "2340.00", "tp": "2370.00", "...": "..."}]
}
```
Decimal values are strings to avoid float rounding.

## Security rules
- Ingest endpoint requires a per-account bearer token (hashed at rest), HTTPS when not localhost,
  rate-limited, payload size-limited.
- Collector/EA only make outbound requests; no listening port on the terminal machine.
- Broker passwords are never sent to or stored by the web app.

## Mock adapter
Generates a deterministic, seeded dataset (multiple symbols, partial closes, breakevens, commissions,
swaps, missing SL/TP, midnight-crossing trades). Accounts created from it have `is_simulated = true`
and the UI shows a "Simulated data" badge.
