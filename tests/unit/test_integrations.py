from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.integrations.csv.adapter import CsvImportError, csv_to_batch, parse_positions_csv
from app.integrations.mock.adapter import MockAdapter
from app.integrations.mt4.normalize import Mt4Ticket, tickets_to_deals
from app.integrations.mt5.normalize import account_from_mt5, deal_from_mt5, order_from_mt5
from app.models.enums import (
    AccountType,
    AssetClass,
    DealEntry,
    DealType,
    MarginMode,
    ServerOffsetMode,
)
from app.utils.symbols import base_symbol, classify, derive_pip
from app.utils.timeconv import ServerOffsetUnknown, server_to_utc


def test_mt5_deal_uses_server_time_and_maps_enums():
    d = deal_from_mt5({"ticket": 101, "order": 55, "position_id": 55, "symbol": "EURUSD",
                       "type": 1, "entry": 1, "time": 1767607200, "time_msc": 1767607200123,
                       "price": 1.1, "volume": 0.5, "profit": -12.3, "commission": -1.75,
                       "swap": 0.0, "fee": 0.0, "sl": 0.0, "tp": 1.09, "magic": 0,
                       "comment": "", "reason": 3})
    assert d.time == datetime(2026, 1, 5, 10, 0, 0, 123000)
    assert d.time.tzinfo is None
    assert d.deal_type == DealType.SELL and d.entry == DealEntry.OUT
    assert d.profit == Decimal("-12.3") and d.sl is None and d.tp == Decimal("1.09")


def test_mt5_account_hashes_login_and_maps_modes():
    acc = account_from_mt5({"login": 123456, "server": "Broker-Live", "company": "Broker",
                            "currency": "usd", "trade_mode": 2, "margin_mode": 2})
    assert "123456" not in acc.login_hash and len(acc.login_hash) == 64
    assert acc.account_type == AccountType.REAL and acc.margin_mode == MarginMode.HEDGING
    assert acc.currency == "USD"


def test_mt5_order_keeps_initial_sl_tp():
    o = order_from_mt5({"ticket": 55, "position_id": 55, "symbol": "EURUSD", "type": 0,
                        "time_setup": 1767607200, "time_done": 1767607200,
                        "volume_initial": 1.0, "price_open": 1.1, "sl": 1.095, "tp": 1.11})
    assert o.order_type == "BUY" and o.sl == Decimal("1.095")


def _t(ticket, lots, profit, comment=None, close="2026-01-05T12:00:00"):
    return Mt4Ticket(ticket=ticket, symbol="EURUSD", type=0, lots=Decimal(lots),
                     open_time=datetime(2026, 1, 5, 10), close_time=datetime.fromisoformat(close),
                     open_price=Decimal("1.1"), close_price=Decimal("1.101"),
                     profit=Decimal(profit), comment=comment)


def test_mt4_partial_close_chain_becomes_one_position():
    deals = tickets_to_deals([
        _t("100", "0.5", "5", comment="to #101"),
        _t("101", "0.5", "8", comment="from #100", close="2026-01-05T14:00:00"),
    ])
    ins = [d for d in deals if d.entry == DealEntry.IN]
    outs = [d for d in deals if d.entry == DealEntry.OUT]
    assert len(ins) == 1 and ins[0].volume == Decimal("1.0")
    assert {d.external_position_id for d in deals} == {"100"}
    assert sum(d.profit for d in outs) == Decimal("13")


def test_mt4_balance_and_pending_tickets():
    deals = tickets_to_deals([
        Mt4Ticket(ticket="1", type=6, open_time=datetime(2026, 1, 1), profit=Decimal("1000")),
        Mt4Ticket(ticket="2", symbol="EURUSD", type=2, open_time=datetime(2026, 1, 1)),
    ])
    assert len(deals) == 1 and deals[0].deal_type == DealType.BALANCE


CSV = """Ticket,Symbol,Type,Volume,Open Time,Open Price,Close Time,Close Price,S/L,T/P,Commission,Swap,Profit
1,XAUUSD,buy,0.10,2026.01.05 10:00:00,2350.00,2026.01.05 11:00:00,2355.00,2340,0,-0.70,0,50.00
2,EURUSD,sell,1.00,2026.01.06 09:00,1.1000,2026.01.06 15:00,1.0990,,,-7.00,-1.20,100.00
"""


def test_csv_parses_statement_layout():
    tickets = parse_positions_csv(CSV)
    assert len(tickets) == 2
    assert tickets[0].tp is None or tickets[0].tp == 0
    batch = csv_to_batch(CSV, login_hash="csv-00000001", currency="usd",
                         server_utc_offset_minutes=120)
    assert len(batch.deals) == 4 and batch.account.currency == "USD"


def test_csv_reports_missing_columns_and_bad_rows():
    with pytest.raises(CsvImportError, match="Missing required"):
        parse_positions_csv("symbol,profit\nEURUSD,1\n")
    with pytest.raises(CsvImportError, match="Row 2"):
        parse_positions_csv("ticket,type,open_time,profit\n1,buy,2026-01-01 10:00,abc\n")


def test_mock_adapter_is_deterministic_and_balanced():
    end = datetime(2026, 6, 1, tzinfo=UTC)
    a = MockAdapter(seed=7, positions=40, end=end).fetch_batch()
    b = MockAdapter(seed=7, positions=40, end=end).fetch_batch()
    assert a.model_dump() == b.model_dump()
    for pos in {d.external_position_id for d in a.deals if d.external_position_id}:
        legs = [d for d in a.deals if d.external_position_id == pos]
        vin = sum(d.volume for d in legs if d.entry == DealEntry.IN)
        vout = sum(d.volume for d in legs if d.entry == DealEntry.OUT)
        assert vin == vout
    assert all(d.time.tzinfo is not None for d in a.deals)


@pytest.mark.parametrize("mode,minutes,batch,expected_hour", [
    (ServerOffsetMode.FIXED, 120, None, 8),
    (ServerOffsetMode.AUTO, None, 180, 7),
    (ServerOffsetMode.AUTO, 120, None, 8),
])
def test_server_to_utc_fixed_and_auto(mode, minutes, batch, expected_hour):
    assert server_to_utc(datetime(2026, 1, 5, 10), mode, minutes, batch) == datetime(
        2026, 1, 5, expected_hour, tzinfo=UTC)


def test_server_to_utc_ny_close_follows_us_dst():
    winter = server_to_utc(datetime(2026, 1, 5, 10), ServerOffsetMode.NY_CLOSE)
    summer = server_to_utc(datetime(2026, 7, 6, 10), ServerOffsetMode.NY_CLOSE)
    assert winter.hour == 8 and summer.hour == 7


def test_server_to_utc_unknown_offset_raises_and_aware_passthrough():
    with pytest.raises(ServerOffsetUnknown):
        server_to_utc(datetime(2026, 1, 5, 10), ServerOffsetMode.AUTO)
    aware = datetime(2026, 1, 5, 10, tzinfo=UTC)
    assert server_to_utc(aware, ServerOffsetMode.AUTO) == aware


@pytest.mark.parametrize("symbol,digits,point,cls,pip", [
    ("EURUSD", 5, "0.00001", AssetClass.FX, "0.0001"),
    ("USDJPY.m", 3, "0.001", AssetClass.FX, "0.01"),
    ("GBPUSD", 4, "0.0001", AssetClass.FX, "0.0001"),
    ("XAUUSDm", 2, "0.01", AssetClass.METAL, "0.1"),
    ("US30", 1, "0.1", AssetClass.OTHER, "0.1"),
])
def test_symbol_classification_and_pip(symbol, digits, point, cls, pip):
    asset = classify(symbol)
    assert asset == cls
    size, label = derive_pip(symbol, digits, Decimal(point), asset)
    assert size == Decimal(pip) and label


def test_base_symbol_strips_suffix():
    assert base_symbol("EURUSD.raw") == "EURUSD"
    assert base_symbol("XAUUSD-ECN") == "XAUUSD"
