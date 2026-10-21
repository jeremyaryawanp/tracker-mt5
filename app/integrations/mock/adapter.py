"""Deterministic SIMULATED trading history for development and demos.

Accounts created from this adapter are flagged ``is_simulated``; the data is not real trading.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import AccountType, DealEntry, DealType, MarginMode, Platform, SyncSource
from app.schemas.ingest import IngestAccount, IngestBatch, IngestDeal, IngestOrder, IngestSymbol


@dataclass(frozen=True)
class _Spec:
    symbol: str
    digits: int
    contract: Decimal
    pip: Decimal
    base_price: Decimal


SPECS = [
    _Spec("XAUUSD", 2, Decimal(100), Decimal("0.1"), Decimal("2350")),
    _Spec("EURUSD", 5, Decimal(100000), Decimal("0.0001"), Decimal("1.0850")),
    _Spec("GBPUSD", 5, Decimal(100000), Decimal("0.0001"), Decimal("1.2700")),
    _Spec("USDJPY", 3, Decimal(100000), Decimal("0.01"), Decimal("151.50")),
]
SETUPS = ["Liquidity Sweep + FVG", "London Breakout", "CISD Reversal", "Asia Range Fade"]
MISTAKES = ["Early Entry", "Moved SL", "Oversized", "FOMO", "No Confirmation"]
EMOTIONS = ["Calm", "Confident", "Anxious", "Impatient", "Revenge"]
COMMISSION_PER_LOT_SIDE = Decimal("3.50")
CENT = Decimal("0.01")


def _q(v: Decimal, places: int) -> Decimal:
    return v.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


class MockAdapter:
    name = "mock"

    def __init__(self, seed: int = 42, positions: int = 160, days: int = 120,
                 end: datetime | None = None, initial_balance: Decimal = Decimal("10000")):
        self.seed = seed
        self.positions = positions
        self.days = days
        self.end = (end or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
        self.initial_balance = initial_balance
        self.annotations: dict[str, dict] = {}

    def fetch_batch(self, range_from: datetime | None = None,
                    range_to: datetime | None = None) -> IngestBatch:
        rng = random.Random(self.seed)
        start = self.end - timedelta(days=self.days)
        deals: list[IngestDeal] = [IngestDeal(
            external_deal_id="SIM-BAL-1", deal_type=DealType.BALANCE, time=start,
            profit=self.initial_balance, comment="Simulated deposit",
        )]
        orders: list[IngestOrder] = []
        self.annotations = {}
        deal_no = 1000
        for i in range(self.positions):
            spec = rng.choice(SPECS)
            pos_id = f"SIM-{i + 1:05d}"
            open_t = start + timedelta(minutes=rng.randint(60, self.days * 24 * 60 - 3000))
            while open_t.weekday() >= 5:
                open_t += timedelta(days=1)
            hold = timedelta(minutes=rng.choice([rng.randint(5, 240), rng.randint(240, 1800)]))
            close_t = open_t + hold
            buy = rng.random() < 0.55
            vol = _q(Decimal(rng.choice([1, 2, 5, 10, 20, 50])) / 100, 2)
            sl_pips = Decimal(rng.randint(10, 40)) * (Decimal(10) if spec.symbol == "XAUUSD" else 1)
            tp_pips = _q(sl_pips * Decimal(str(rng.choice([1, 1.5, 2, 3]))), 0)
            price = _q(spec.base_price * Decimal(str(1 + rng.uniform(-0.03, 0.03))), spec.digits)
            sign = 1 if buy else -1
            sl = _q(price - sign * sl_pips * spec.pip, spec.digits)
            tp = _q(price + sign * tp_pips * spec.pip, spec.digits)
            roll = rng.random()
            breakeven = roll < 0.05
            if breakeven:
                exit_price = price
            elif roll < 0.48:
                exit_price = tp if rng.random() < 0.6 else _q(
                    price + sign * tp_pips * spec.pip * Decimal(str(rng.uniform(0.3, 0.9))),
                    spec.digits)
            else:
                exit_price = sl if rng.random() < 0.7 else _q(
                    price - sign * sl_pips * spec.pip * Decimal(str(rng.uniform(0.2, 0.9))),
                    spec.digits)
            has_sltp = rng.random() > 0.12
            partial = not breakeven and rng.random() < 0.12
            nights = sum(1 for d in range(1, (close_t.date() - open_t.date()).days + 1))
            commission_side = (Decimal(0) if breakeven
                               else -_q(COMMISSION_PER_LOT_SIDE * vol, 2))
            deal_no += 1
            deals.append(IngestDeal(
                external_deal_id=f"SIM-D{deal_no}", external_order_id=pos_id,
                external_position_id=pos_id, symbol=spec.symbol,
                deal_type=DealType.BUY if buy else DealType.SELL, entry=DealEntry.IN,
                time=open_t, price=price, volume=vol, commission=commission_side,
            ))
            orders.append(IngestOrder(
                external_order_id=pos_id, external_position_id=pos_id, symbol=spec.symbol,
                order_type="BUY" if buy else "SELL", time_setup=open_t, time_done=open_t,
                volume_initial=vol, price_open=price,
                sl=sl if has_sltp else None, tp=tp if has_sltp else None,
            ))
            exits = [(vol, exit_price, close_t)]
            if partial and vol >= Decimal("0.02"):
                first = _q(vol / 2, 2)
                mid_price = _q((price + exit_price) / 2, spec.digits)
                exits = [(first, mid_price, open_t + hold / 2), (vol - first, exit_price, close_t)]
            for n, (v, px, t) in enumerate(exits):
                diff = (px - price) * sign * v * spec.contract
                profit = diff / px if spec.symbol.startswith("USD") else diff
                swap = Decimal(0) if breakeven or n < len(exits) - 1 else -_q(
                    Decimal("0.8") * vol * nights, 2)
                c = Decimal(0) if breakeven else -_q(COMMISSION_PER_LOT_SIDE * v, 2)
                deal_no += 1
                deals.append(IngestDeal(
                    external_deal_id=f"SIM-D{deal_no}", external_order_id=f"{pos_id}-X{n}",
                    external_position_id=pos_id, symbol=spec.symbol,
                    deal_type=DealType.SELL if buy else DealType.BUY, entry=DealEntry.OUT,
                    time=t, price=px, volume=v, profit=_q(profit, 2), commission=c, swap=swap,
                ))
            if rng.random() < 0.7:
                self.annotations[pos_id] = {
                    "setup_name": rng.choice(SETUPS),
                    "rule_followed": rng.random() < 0.7,
                    "emotional_state": rng.choice(EMOTIONS),
                    "entry_timeframe": rng.choice(["M1", "M5", "M15"]),
                    "higher_timeframe_context": rng.choice(
                        ["H4 bullish", "H4 bearish", "D1 range"]),
                    "mistakes": rng.sample(MISTAKES, k=rng.choice([0, 0, 1, 2])),
                    "ict_tags": rng.sample(["Liquidity Sweep", "Fair Value Gap (FVG)",
                                            "Change in State of Delivery (CISD)",
                                            "Previous Day High/Low"], k=rng.choice([0, 1, 2])),
                    "personal_notes": "Simulated annotation (demo data).",
                }
        symbols = [IngestSymbol(symbol=s.symbol, digits=s.digits, point=Decimal(10) ** -s.digits,
                                contract_size=s.contract, profit_currency="USD" if
                                not s.symbol.startswith("USD") else s.symbol[3:])
                   for s in SPECS]
        return IngestBatch(
            source=SyncSource.MOCK,
            account=IngestAccount(platform=Platform.MOCK, login_hash=f"simulated-{self.seed:08d}",
                                  broker_name="Simulated Broker", broker_server="SIMULATED",
                                  currency="USD", account_type=AccountType.DEMO,
                                  margin_mode=MarginMode.HEDGING,
                                  initial_balance=self.initial_balance),
            range_from=start, range_to=self.end, symbols=symbols, deals=deals, orders=orders,
        )
