"""Pure conversion of MetaTrader5-package records (``record._asdict()``) into ingest models.

MT5 returns times as epoch seconds expressed in broker *server* time, so they are converted to
naive server datetimes here and to UTC later using the account's offset configuration.
"""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.models.enums import AccountType, DealEntry, DealType, MarginMode, Platform, SyncSource
from app.schemas.ingest import IngestAccount, IngestDeal, IngestOrder, IngestSymbol

DEAL_TYPES = {0: DealType.BUY, 1: DealType.SELL, 2: DealType.BALANCE, 3: DealType.CREDIT,
              7: DealType.COMMISSION, 8: DealType.COMMISSION, 9: DealType.COMMISSION,
              10: DealType.COMMISSION}
DEAL_ENTRIES = {0: DealEntry.IN, 1: DealEntry.OUT, 2: DealEntry.INOUT, 3: DealEntry.OUT_BY}
ORDER_TYPES = {0: "BUY", 1: "SELL", 2: "BUY_LIMIT", 3: "SELL_LIMIT", 4: "BUY_STOP",
               5: "SELL_STOP", 6: "BUY_STOP_LIMIT", 7: "SELL_STOP_LIMIT", 8: "CLOSE_BY"}
TRADE_MODES = {0: AccountType.DEMO, 1: AccountType.CONTEST, 2: AccountType.REAL}
MARGIN_MODES = {0: MarginMode.NETTING, 1: MarginMode.NETTING, 2: MarginMode.HEDGING}


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def server_time(seconds: int | None, msc: int | None = None) -> datetime | None:
    if msc:
        return datetime.fromtimestamp(msc / 1000, UTC).replace(tzinfo=None)
    if seconds:
        return datetime.fromtimestamp(seconds, UTC).replace(tzinfo=None)
    return None


def login_hash(platform: str, server: str | None, login: int | str) -> str:
    return hashlib.sha256(f"{platform}:{server or ''}:{login}".encode()).hexdigest()


def account_from_mt5(info: dict) -> IngestAccount:
    return IngestAccount(
        platform=Platform.MT5,
        login_hash=login_hash("MT5", info.get("server"), info["login"]),
        broker_name=info.get("company"),
        broker_server=info.get("server"),
        currency=info.get("currency") or "XXX",
        account_type=TRADE_MODES.get(info.get("trade_mode"), AccountType.UNKNOWN),
        margin_mode=MARGIN_MODES.get(info.get("margin_mode"), MarginMode.UNKNOWN),
    )


def deal_from_mt5(d: dict) -> IngestDeal:
    position_id = d.get("position_id")
    return IngestDeal(
        external_deal_id=str(d["ticket"]),
        external_order_id=str(d["order"]) if d.get("order") else None,
        external_position_id=str(position_id) if position_id else None,
        symbol=d.get("symbol") or None,
        deal_type=DEAL_TYPES.get(d.get("type"), DealType.OTHER),
        entry=DEAL_ENTRIES.get(d.get("entry"), DealEntry.NONE),
        time=server_time(d.get("time"), d.get("time_msc")),
        price=_dec(d.get("price")),
        volume=_dec(d.get("volume")),
        profit=_dec(d.get("profit")) or Decimal("0"),
        commission=_dec(d.get("commission")) or Decimal("0"),
        swap=_dec(d.get("swap")) or Decimal("0"),
        fee=_dec(d.get("fee")) or Decimal("0"),
        sl=_dec(d.get("sl")),
        tp=_dec(d.get("tp")),
        magic=d.get("magic"),
        comment=(d.get("comment") or None),
        reason=str(d.get("reason")) if d.get("reason") is not None else None,
        raw={k: v for k, v in d.items() if isinstance(v, (int, float, str))},
    )


def order_from_mt5(o: dict) -> IngestOrder:
    return IngestOrder(
        external_order_id=str(o["ticket"]),
        external_position_id=str(o["position_id"]) if o.get("position_id") else None,
        symbol=o.get("symbol") or None,
        order_type=ORDER_TYPES.get(o.get("type"), str(o.get("type"))),
        time_setup=server_time(o.get("time_setup"), o.get("time_setup_msc")),
        time_done=server_time(o.get("time_done"), o.get("time_done_msc")),
        volume_initial=_dec(o.get("volume_initial")),
        price_open=_dec(o.get("price_open")),
        sl=_dec(o.get("sl")),
        tp=_dec(o.get("tp")),
    )


def symbol_from_mt5(s: dict) -> IngestSymbol:
    return IngestSymbol(
        symbol=s["name"],
        digits=s.get("digits"),
        point=_dec(s.get("point")),
        contract_size=_dec(s.get("trade_contract_size")),
        tick_size=_dec(s.get("trade_tick_size")),
        tick_value=_dec(s.get("trade_tick_value")),
        profit_currency=s.get("currency_profit"),
        path=s.get("path"),
    )


SOURCE = SyncSource.MT5_COLLECTOR
