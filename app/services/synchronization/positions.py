"""Rebuild derived positions from raw deals.

Deals sharing ``external_position_id`` form one position (hedging) so partial closes and
scale-ins stay one position. In netting mode an ``INOUT`` deal (reversal) closes the current
segment and opens a new one keyed ``<position_id>#<n>``. Costs come only from the deals that
carry them, so nothing is deducted twice. Annotations reference positions by row id and are
preserved because rows are updated in place.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TradeDeal, TradeOrder, TradePosition, TradingAccount
from app.models.enums import DealEntry, DealType, Direction, PositionStatus, SlTpSource
from app.utils.sessions import session_for

ZERO = Decimal("0")
TRADE_TYPES = (DealType.BUY, DealType.SELL)


@dataclass
class _Segment:
    key: str
    symbol: str
    direction: Direction
    open_time: datetime
    first_in: TradeDeal
    in_volume: Decimal = ZERO
    in_value: Decimal = ZERO
    out_volume: Decimal = ZERO
    out_value: Decimal = ZERO
    profit: Decimal = ZERO
    commission: Decimal = ZERO
    swap: Decimal = ZERO
    fees: Decimal = ZERO
    close_time: datetime | None = None
    exits: int = 0
    last_out: TradeDeal | None = None
    deal_ids: list[str] = field(default_factory=list)

    @property
    def open_volume(self) -> Decimal:
        return self.in_volume - self.out_volume

    def add_costs(self, d: TradeDeal) -> None:
        self.commission += d.commission or ZERO
        self.swap += d.swap or ZERO
        self.fees += d.fee or ZERO
        self.deal_ids.append(d.external_deal_id)

    def add_in(self, d: TradeDeal, volume: Decimal) -> None:
        self.in_volume += volume
        self.in_value += volume * (d.price or ZERO)

    def add_out(self, d: TradeDeal, volume: Decimal) -> None:
        self.out_volume += volume
        self.out_value += volume * (d.price or ZERO)
        self.close_time = d.time_utc
        self.exits += 1
        self.last_out = d


def _direction(d: TradeDeal) -> Direction:
    return Direction.BUY if d.deal_type == DealType.BUY else Direction.SELL


def build_segments(position_id: str, deals: list[TradeDeal]) -> list[_Segment]:
    segments: list[_Segment] = []
    current: _Segment | None = None

    def start(d: TradeDeal, direction: Direction) -> _Segment:
        n = len(segments) + 1
        seg = _Segment(key=position_id if n == 1 else f"{position_id}#{n}",
                       symbol=d.symbol or "", direction=direction, open_time=d.time_utc,
                       first_in=d)
        segments.append(seg)
        return seg

    for d in deals:
        if d.deal_type not in TRADE_TYPES:
            continue
        vol = d.volume or ZERO
        if d.entry == DealEntry.IN or current is None and d.entry != DealEntry.INOUT:
            if current is None or current.open_volume <= 0:
                current = start(d, _direction(d) if d.entry == DealEntry.IN
                                else Direction.SELL if d.deal_type == DealType.BUY
                                else Direction.BUY)
            if d.entry == DealEntry.IN:
                current.add_in(d, vol)
            else:  # OUT seen before its IN (history window cut): keep the exit
                current.add_out(d, vol)
                current.profit += d.profit or ZERO
            current.add_costs(d)
        elif d.entry in (DealEntry.OUT, DealEntry.OUT_BY):
            current.add_out(d, vol)
            current.profit += d.profit or ZERO
            current.add_costs(d)
        elif d.entry == DealEntry.INOUT:
            closing = max(current.open_volume, ZERO) if current else ZERO
            if current is not None and closing > 0:
                current.add_out(d, closing)
                current.profit += d.profit or ZERO
                current.add_costs(d)
            current = start(d, _direction(d))
            current.add_in(d, vol - closing)
            if closing == 0:
                current.add_costs(d)
    return segments


def _initial_sl_tp(seg: _Segment, orders: dict[str, TradeOrder]):
    order = orders.get(seg.first_in.external_order_id or "")
    if order and (order.sl_price or order.tp_price):
        return order.sl_price, order.tp_price, SlTpSource.OPEN_ORDER
    if seg.first_in.sl_price or seg.first_in.tp_price:
        return seg.first_in.sl_price, seg.first_in.tp_price, SlTpSource.OPEN_DEAL
    if seg.last_out and (seg.last_out.sl_price or seg.last_out.tp_price):
        return seg.last_out.sl_price, seg.last_out.tp_price, SlTpSource.LAST_KNOWN
    return None, None, SlTpSource.NONE


def rebuild_positions(session: Session, account: TradingAccount, position_ids: set[str]) -> int:
    if not position_ids:
        return 0
    sessions_spec = get_settings().trading_sessions
    ids = sorted(position_ids)
    rebuilt = 0
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        deals_by_pos: dict[str, list[TradeDeal]] = {p: [] for p in chunk}
        for d in session.scalars(select(TradeDeal).where(
            TradeDeal.account_id == account.id, TradeDeal.external_position_id.in_(chunk)
        ).order_by(TradeDeal.time_utc, TradeDeal.id)):
            deals_by_pos[d.external_position_id].append(d)
        order_ids = {d.external_order_id for ds in deals_by_pos.values() for d in ds
                     if d.external_order_id}
        orders = {o.external_order_id: o for o in session.scalars(select(TradeOrder).where(
            TradeOrder.account_id == account.id, TradeOrder.external_order_id.in_(order_ids)
        ))} if order_ids else {}
        existing = _existing(session, account, chunk)

        for pos_id in chunk:
            produced = set()
            for seg in build_segments(pos_id, deals_by_pos[pos_id]):
                if seg.in_volume <= 0 and seg.out_volume <= 0:
                    continue
                row = existing.get(seg.key)
                if row is None:
                    row = TradePosition(account_id=account.id, external_position_id=seg.key)
                    session.add(row)
                _fill(row, seg, account, orders, sessions_spec)
                produced.add(seg.key)
                rebuilt += 1
            for key, row in existing.items():
                if _base_key(key) == pos_id and key not in produced:
                    session.delete(row)
    session.flush()
    return rebuilt


def _base_key(key: str) -> str:
    return key.split("#", 1)[0]


def _existing(session: Session, account: TradingAccount, chunk: list[str]):
    wanted = set(chunk)
    rows = session.scalars(select(TradePosition).where(
        TradePosition.account_id == account.id,
        TradePosition.external_position_id.in_(chunk)
        | TradePosition.external_position_id.contains("#"),
    ))
    return {r.external_position_id: r for r in rows if _base_key(r.external_position_id) in wanted}


def _fill(row: TradePosition, seg: _Segment, account: TradingAccount,
          orders: dict[str, TradeOrder], sessions_spec: str) -> None:
    closed = seg.out_volume > 0 and seg.open_volume <= 0
    volume = seg.in_volume if seg.in_volume > 0 else seg.out_volume
    sl, tp, source = _initial_sl_tp(seg, orders)
    row.symbol = seg.symbol
    row.direction = seg.direction
    row.status = PositionStatus.CLOSED if closed else PositionStatus.OPEN
    row.volume_lots = volume
    row.open_time = seg.open_time
    row.close_time = seg.close_time if closed else None
    row.open_price = (seg.in_value / seg.in_volume) if seg.in_volume > 0 else (
        seg.first_in.price or ZERO)
    row.close_price = (seg.out_value / seg.out_volume) if seg.out_volume > 0 else None
    row.realized_gross_profit = seg.profit
    row.commission = seg.commission
    row.swap = seg.swap
    row.fees = seg.fees
    row.realized_net_profit = seg.profit + seg.commission + seg.swap + seg.fees
    row.initial_sl_price = sl
    row.initial_tp_price = tp
    row.sl_tp_source = source
    row.exit_count = seg.exits
    row.trading_session = session_for(seg.open_time, sessions_spec)
    row.account_currency = account.account_currency
    row.source_metadata = {
        "deal_ids": seg.deal_ids,
        "open_volume_remaining": str(seg.open_volume) if seg.open_volume > 0 else "0",
        "incomplete_history": seg.in_volume <= 0,
    }


def rebuild_account(session: Session, account: TradingAccount) -> int:
    ids = set(session.scalars(select(TradeDeal.external_position_id).where(
        TradeDeal.account_id == account.id, TradeDeal.external_position_id.is_not(None)
    ).distinct()))
    ids |= {_base_key(k) for k in session.scalars(select(TradePosition.external_position_id)
            .where(TradePosition.account_id == account.id))}
    return rebuild_positions(session, account, ids)
