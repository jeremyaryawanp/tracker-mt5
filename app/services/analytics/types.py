from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class PositionRow:
    """Closed position flattened with symbol spec and (optional) annotation data."""

    id: int
    account_id: int
    external_position_id: str
    symbol: str
    direction: str
    volume: Decimal
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    close_price: Decimal | None
    gross: Decimal
    commission: Decimal
    swap: Decimal
    fees: Decimal
    net: Decimal
    currency: str = "USD"
    sl: Decimal | None = None
    tp: Decimal | None = None
    sl_tp_source: str = "NONE"
    exit_count: int = 1
    session: str = "OFF_SESSION"
    pip_size: Decimal | None = None
    pip_label: str | None = None
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    contract_size: Decimal | None = None
    profit_currency: str | None = None
    setup: str | None = None
    rule_followed: bool | None = None
    emotional_state: str | None = None
    tags: tuple[str, ...] = ()
    mistakes: tuple[str, ...] = ()
    is_simulated: bool = False


@dataclass(frozen=True)
class CashFlow:
    time: datetime
    amount: Decimal
    currency: str


@dataclass
class AnalyticsFilter:
    account_ids: list[int] | None = None
    date_from: date | None = None
    date_to: date | None = None
    symbols: list[str] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)
    sessions: list[str] = field(default_factory=list)
    setups: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    outcome: str | None = None  # WIN / LOSS / BREAKEVEN
