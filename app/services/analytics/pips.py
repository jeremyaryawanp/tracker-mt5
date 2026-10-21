"""Pip and risk conversions. Return None when the inputs needed are unavailable."""

from decimal import Decimal

from app.services.analytics.types import PositionRow

ZERO = Decimal("0")
TRUSTED_SLTP = ("OPEN_ORDER", "OPEN_DEAL")


def _sign(p: PositionRow) -> int:
    return 1 if p.direction == "BUY" else -1


def to_pips(price_diff: Decimal, pip_size: Decimal | None) -> Decimal | None:
    if pip_size is None or pip_size == 0:
        return None
    return price_diff / pip_size


def initial_sl(p: PositionRow) -> Decimal | None:
    """Initial SL usable for risk; MT4 last-known SL is not trusted as initial risk."""
    return p.sl if p.sl is not None and p.sl_tp_source in TRUSTED_SLTP else None


def initial_tp(p: PositionRow) -> Decimal | None:
    return p.tp if p.tp is not None and p.sl_tp_source in TRUSTED_SLTP else None


def planned_sl_pips(p: PositionRow) -> Decimal | None:
    sl = initial_sl(p)
    return None if sl is None else to_pips((p.open_price - sl) * _sign(p), p.pip_size)


def planned_tp_pips(p: PositionRow) -> Decimal | None:
    tp = initial_tp(p)
    return None if tp is None else to_pips((tp - p.open_price) * _sign(p), p.pip_size)


def actual_exit_pips(p: PositionRow) -> Decimal | None:
    if p.close_price is None:
        return None
    return to_pips((p.close_price - p.open_price) * _sign(p), p.pip_size)


def planned_rr(p: PositionRow) -> Decimal | None:
    sl, tp = initial_sl(p), initial_tp(p)
    if sl is None or tp is None or sl == p.open_price:
        return None
    risk = (p.open_price - sl) * _sign(p)
    reward = (tp - p.open_price) * _sign(p)
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def value_per_price_unit(p: PositionRow, account_currency: str | None = None) -> Decimal | None:
    """Account-currency value of a 1.0 price move for the whole position volume."""
    if p.tick_size and p.tick_value:
        return p.tick_value / p.tick_size * p.volume
    if p.close_price is not None and p.close_price != p.open_price and p.gross != 0:
        implied = p.gross / ((p.close_price - p.open_price) * _sign(p))
        if implied > 0:
            return implied
    if p.contract_size and p.profit_currency and p.profit_currency == (account_currency
                                                                      or p.currency):
        return p.contract_size * p.volume
    return None


def initial_risk(p: PositionRow) -> Decimal | None:
    sl = initial_sl(p)
    if sl is None:
        return None
    distance = (p.open_price - sl) * _sign(p)
    if distance <= 0:  # SL at/through entry: no initial risk defined
        return None
    vpu = value_per_price_unit(p)
    return None if vpu is None else distance * vpu


def r_multiple(p: PositionRow) -> Decimal | None:
    risk = initial_risk(p)
    return None if not risk else p.net / risk
