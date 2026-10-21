"""TradeJournal AI — MetaTrader 5 history collector (READ-ONLY).

Runs on the Windows machine where the MT5 terminal is installed and logged in. It reads
closed-deal history with the official ``MetaTrader5`` package and pushes normalized batches to
``POST /api/v1/ingest``. It never calls ``order_send``/``order_check`` or any other trading
function, and never transmits the broker password or account number (only a SHA-256 hash).

Usage (PowerShell):
    pip install "MetaTrader5" httpx pydantic
    $env:TJ_URL = "http://192.168.1.10:8000"
    $env:TJ_TOKEN = "<ingest token from the Accounts page>"
    python -m collector.mt5_collector --days 365          # one-off backfill
    python -m collector.mt5_collector --loop 300          # sync every 5 minutes
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.integrations.mt5.normalize import (
    SOURCE,
    account_from_mt5,
    deal_from_mt5,
    order_from_mt5,
    symbol_from_mt5,
)
from app.schemas.ingest import IngestBatch

log = logging.getLogger("mt5_collector")
STATE_FILE = Path(os.environ.get("TJ_STATE_FILE", "tj_collector_state.json"))
OVERLAP = timedelta(days=2)
FORBIDDEN = ("order_send", "order_check", "Buy", "Sell", "Close")


def _mt5():
    try:
        import MetaTrader5 as mt5  # noqa: N813  (Windows-only package)
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("MetaTrader5 package not installed (Windows only).") from exc
    return mt5


def detect_server_offset_minutes(mt5, symbol: str = "EURUSD") -> int | None:
    """Estimate broker offset from the latest tick time vs real UTC (rounded to 30 min)."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or not tick.time:
        return None
    server_now = datetime.fromtimestamp(tick.time, UTC)
    delta = server_now - datetime.now(UTC)
    if abs(delta) > timedelta(hours=15):
        return None
    minutes = int(round(delta.total_seconds() / 1800.0)) * 30
    # A stale tick (market closed) leaves a large residual; refuse to guess then.
    if abs(delta.total_seconds() - minutes * 60) > 300:
        return None
    return minutes


class Mt5Adapter:
    name = "mt5"

    def __init__(self, terminal_path: str | None = None, offset_minutes: int | None = None,
                 offset_symbol: str = "EURUSD"):
        self.mt5 = _mt5()
        kwargs = {"path": terminal_path} if terminal_path else {}
        if not self.mt5.initialize(**kwargs):
            raise SystemExit(f"MT5 initialize() failed: {self.mt5.last_error()}")
        self.offset_minutes = offset_minutes
        self.offset_symbol = offset_symbol

    def close(self) -> None:
        self.mt5.shutdown()

    def fetch_batch(self, range_from: datetime, range_to: datetime) -> IngestBatch:
        mt5 = self.mt5
        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"Terminal not logged in: {mt5.last_error()}")
        offset = self.offset_minutes
        if offset is None:
            offset = detect_server_offset_minutes(mt5, self.offset_symbol)
        # history_* take server-time datetimes; pad the window by the max broker offset.
        deals = mt5.history_deals_get(range_from - timedelta(hours=14),
                                      range_to + timedelta(hours=14)) or ()
        orders = mt5.history_orders_get(range_from - timedelta(hours=14),
                                        range_to + timedelta(hours=14)) or ()
        names = sorted({d.symbol for d in deals if d.symbol})
        symbols = [s for s in (mt5.symbol_info(n) for n in names) if s is not None]
        return IngestBatch(
            source=SOURCE,
            account=account_from_mt5(info._asdict()),
            range_from=range_from,
            range_to=range_to,
            server_utc_offset_minutes=offset,
            symbols=[symbol_from_mt5(s._asdict()) for s in symbols],
            deals=[deal_from_mt5(d._asdict()) for d in deals],
            orders=[order_from_mt5(o._asdict()) for o in orders],
        )


def push(url: str, token: str, batch: IngestBatch, attempts: int = 5) -> dict:
    """POST with exponential backoff on network errors and 5xx; 4xx are not retried."""
    payload = batch.model_dump(mode="json")
    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            resp = httpx.post(f"{url.rstrip('/')}/api/v1/ingest", json=payload, timeout=120,
                              headers={"Authorization": f"Bearer {token}"})
            if resp.status_code < 500:
                body = resp.json()
                if resp.status_code >= 400:
                    log.error("ingest rejected (%s): %s", resp.status_code, body)
                return body
            log.warning("server error %s (attempt %s)", resp.status_code, attempt)
        except httpx.HTTPError as exc:
            log.warning("network error %s (attempt %s)", type(exc).__name__, attempt)
        time.sleep(delay)
        delay = min(delay * 2, 120)
    raise RuntimeError("ingest failed after retries")


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def sync_once(adapter, url: str, token: str, days: int) -> dict:
    now = datetime.now(UTC)
    state = load_state()
    last = state.get("last_success_to")
    start = (datetime.fromisoformat(last) - OVERLAP) if last else now - timedelta(days=days)
    batch = adapter.fetch_batch(start, now)
    result = push(url, token, batch)
    if result.get("status") == "SUCCESS":
        save_state({"last_success_to": now.isoformat()})
    log.info("sync result: %s", result)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", default=os.environ.get("TJ_URL", "http://127.0.0.1:8000"))
    p.add_argument("--token", default=os.environ.get("TJ_TOKEN"))
    p.add_argument("--days", type=int, default=365, help="initial backfill window")
    p.add_argument("--loop", type=int, default=0, help="seconds between syncs (0 = once)")
    p.add_argument("--terminal-path", default=os.environ.get("TJ_TERMINAL_PATH"))
    p.add_argument("--offset-minutes", type=int, default=None,
                   help="broker server UTC offset; auto-detected from ticks if omitted")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.token:
        print("TJ_TOKEN / --token is required", file=sys.stderr)
        return 2
    adapter = Mt5Adapter(args.terminal_path, args.offset_minutes)
    try:
        while True:
            try:
                sync_once(adapter, args.url, args.token, args.days)
            except Exception as exc:  # keep the loop alive; error already logged/sent
                log.error("sync failed: %s", exc)
                if not args.loop:
                    return 1
            if not args.loop:
                return 0
            time.sleep(args.loop)
    finally:
        adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
