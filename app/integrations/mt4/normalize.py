"""Convert MT4 closed tickets (from the MQL4 EA or a positions CSV) into synthetic deals.

MT4 has no deal objects. Each closed ticket yields an OUT deal; the root ticket of a
partial-close chain (``comment = "from #<ticket>"``) yields the single IN deal for the whole
original volume. Commission/swap/profit stay on the ticket that reported them.
"""

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import DealEntry, DealType
from app.schemas.ingest import IngestDeal

FROM_RE = re.compile(r"from\s*#\s*(\d+)", re.IGNORECASE)


class Mt4Ticket(BaseModel):
    ticket: str
    symbol: str = ""
    type: int = Field(description="0=BUY 1=SELL 6=BALANCE 7=CREDIT; 2-5 pending (ignored)")
    lots: Decimal = Decimal("0")
    open_time: datetime
    close_time: datetime | None = None
    open_price: Decimal | None = None
    close_price: Decimal | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None
    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")
    profit: Decimal = Decimal("0")
    comment: str | None = None
    magic: int | None = None


def _root(ticket: str, parents: dict[str, str]) -> str:
    seen = set()
    while ticket in parents and ticket not in seen:
        seen.add(ticket)
        ticket = parents[ticket]
    return ticket


def tickets_to_deals(tickets: list[Mt4Ticket]) -> list[IngestDeal]:
    by_id = {t.ticket: t for t in tickets}
    parents: dict[str, str] = {}
    for t in tickets:
        m = FROM_RE.search(t.comment or "")
        if m and m.group(1) in by_id:
            parents[t.ticket] = m.group(1)

    deals: list[IngestDeal] = []
    chain_volume: dict[str, Decimal] = {}
    for t in tickets:
        if t.type in (0, 1) and t.close_time is not None:
            root = _root(t.ticket, parents)
            chain_volume[root] = chain_volume.get(root, Decimal("0")) + t.lots

    for t in tickets:
        if t.type in (6, 7):
            deals.append(IngestDeal(
                external_deal_id=f"{t.ticket}:balance",
                deal_type=DealType.BALANCE if t.type == 6 else DealType.CREDIT,
                entry=DealEntry.NONE, time=t.open_time, profit=t.profit, comment=t.comment,
            ))
            continue
        if t.type not in (0, 1) or t.close_time is None:
            continue
        root = _root(t.ticket, parents)
        side = DealType.BUY if t.type == 0 else DealType.SELL
        opposite = DealType.SELL if t.type == 0 else DealType.BUY
        if root == t.ticket:
            deals.append(IngestDeal(
                external_deal_id=f"{t.ticket}:open", external_order_id=t.ticket,
                external_position_id=root, symbol=t.symbol, deal_type=side,
                entry=DealEntry.IN, time=t.open_time, price=t.open_price,
                volume=chain_volume[root], magic=t.magic,
            ))
        deals.append(IngestDeal(
            external_deal_id=f"{t.ticket}:close", external_order_id=t.ticket,
            external_position_id=root, symbol=t.symbol, deal_type=opposite,
            entry=DealEntry.OUT, time=t.close_time, price=t.close_price, volume=t.lots,
            profit=t.profit, commission=t.commission, swap=t.swap, sl=t.sl, tp=t.tp,
            magic=t.magic, comment=t.comment,
        ))
    return deals
