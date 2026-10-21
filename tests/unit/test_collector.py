import sys
import types
from collections import namedtuple
from datetime import UTC, datetime

import pytest

Deal = namedtuple("Deal", "ticket order position_id symbol type entry time time_msc price volume "
                          "profit commission swap fee sl tp magic comment reason")
Order = namedtuple("Order", "ticket position_id symbol type time_setup time_done volume_initial "
                            "price_open sl tp")
Info = namedtuple("Info", "login server company currency trade_mode margin_mode")
Sym = namedtuple("Sym", "name digits point trade_contract_size trade_tick_size trade_tick_value "
                        "currency_profit path")
Tick = namedtuple("Tick", "time")


@pytest.fixture
def fake_mt5(monkeypatch):
    calls = []
    mod = types.ModuleType("MetaTrader5")
    mod.initialize = lambda **kw: True
    mod.shutdown = lambda: None
    mod.last_error = lambda: (0, "ok")
    mod.account_info = lambda: Info(111, "Demo-Server", "Broker", "USD", 0, 2)
    mod.history_deals_get = lambda a, b: (
        Deal(1, 9, 9, "EURUSD", 0, 0, 1767607200, 0, 1.1, 1.0, 0, -3.5, 0, 0, 0, 0, 0, "", 0),)
    mod.history_orders_get = lambda a, b: (
        Order(9, 9, "EURUSD", 0, 1767607200, 1767607200, 1.0, 1.1, 1.09, 1.12),)
    mod.symbol_info = lambda n: Sym(n, 5, 0.00001, 100000, 0.00001, 1.0, "USD", "Forex\\EURUSD")
    mod.symbol_info_tick = lambda n: Tick(int(datetime.now(UTC).timestamp()) + 7200)

    def forbidden(*a, **k):  # pragma: no cover - must never be called
        calls.append("order_send")
        raise AssertionError("collector must never trade")

    mod.order_send = forbidden
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)
    return calls


def test_mt5_adapter_builds_batch_and_never_trades(fake_mt5):
    from collector.mt5_collector import Mt5Adapter

    adapter = Mt5Adapter()
    batch = adapter.fetch_batch(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 6, tzinfo=UTC))
    assert batch.server_utc_offset_minutes == 120
    assert batch.account.margin_mode == "HEDGING"
    assert batch.orders[0].sl is not None and batch.symbols[0].digits == 5
    assert fake_mt5 == []


def test_sync_once_saves_state_only_on_success(fake_mt5, monkeypatch, tmp_path):
    import collector.mt5_collector as c

    monkeypatch.setattr(c, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(c, "push", lambda url, token, batch: {"status": "FAILED"})
    c.sync_once(c.Mt5Adapter(), "http://x", "t", 30)
    assert not (tmp_path / "state.json").exists()
    monkeypatch.setattr(c, "push", lambda url, token, batch: {"status": "SUCCESS"})
    c.sync_once(c.Mt5Adapter(), "http://x", "t", 30)
    assert "last_success_to" in c.load_state()


def test_collector_source_has_no_trading_calls():
    from pathlib import Path

    for path in [Path("collector/mt5_collector.py"), Path("collector/mt4/TradeJournalExporter.mq4")]:
        text = path.read_text()
        for call in ("order_send(", "OrderSend(", "OrderModify(", "OrderClose("):
            assert call not in text, f"{call} found in {path}"
