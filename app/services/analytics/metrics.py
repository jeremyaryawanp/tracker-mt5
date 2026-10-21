"""Pure, deterministic trading metrics over closed positions (docs/analytics-definitions.md).

All functions take ``PositionRow`` sequences in a single account currency. Callers group by
currency before calling; amounts are never summed across currencies.
"""

import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.analytics import pips
from app.services.analytics.types import CashFlow, PositionRow

ZERO = Decimal("0")
CENT = Decimal("0.01")
WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def outcome(p: PositionRow) -> str:
    n = p.net.quantize(CENT)
    return "WIN" if n > 0 else "LOSS" if n < 0 else "BREAKEVEN"


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, ZERO) / len(values) if values else None


def by_close(rows: Iterable[PositionRow]) -> list[PositionRow]:
    return sorted(rows, key=lambda p: (p.close_time, p.id))


def local_day(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def week_start_of(d: date, week_start: str = "MONDAY") -> date:
    offset = (d.weekday() - WEEKDAYS.index(week_start.upper())) % 7
    return d - timedelta(days=offset)


def profit_factor(gross_profit: Decimal, gross_loss: Decimal) -> tuple[Decimal | None, bool]:
    """Return (value, is_infinite). Both zero -> (None, False)."""
    if gross_loss == 0:
        return None, gross_profit > 0
    return gross_profit / gross_loss, False


def streaks(rows: Sequence[PositionRow]) -> tuple[int, int]:
    best_w = best_l = cur_w = cur_l = 0
    for p in by_close(rows):
        o = outcome(p)
        cur_w = cur_w + 1 if o == "WIN" else 0
        cur_l = cur_l + 1 if o == "LOSS" else 0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


def drawdown(rows: Sequence[PositionRow], starting_balance: Decimal | None = None) -> dict:
    """Realized drawdown on the cumulative net curve ordered by close time."""
    base = starting_balance or ZERO
    cum = peak = base
    max_dd = ZERO
    max_pct: Decimal | None = None
    for p in by_close(rows):
        cum += p.net
        peak = max(peak, cum)
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
            max_pct = (dd / peak * 100) if starting_balance and peak > 0 else None
    return {"max_drawdown": max_dd, "max_drawdown_pct": max_pct}


def daily_pnl(rows: Iterable[PositionRow], tz: ZoneInfo) -> list[dict]:
    days: dict[date, dict] = {}
    for p in rows:
        d = days.setdefault(local_day(p.close_time, tz),
                            {"net": ZERO, "trades": 0, "wins": 0, "losses": 0, "breakevens": 0})
        d["net"] += p.net
        d["trades"] += 1
        d[{"WIN": "wins", "LOSS": "losses", "BREAKEVEN": "breakevens"}[outcome(p)]] += 1
    return [{"date": k, **v} for k, v in sorted(days.items())]


def period_pnl(rows: Iterable[PositionRow], tz: ZoneInfo, period: str = "week",
               week_start: str = "MONDAY") -> list[dict]:
    buckets: dict[date, dict] = {}
    for p in rows:
        d = local_day(p.close_time, tz)
        key = week_start_of(d, week_start) if period == "week" else d.replace(day=1)
        b = buckets.setdefault(key, {"net": ZERO, "trades": 0, "wins": 0})
        b["net"] += p.net
        b["trades"] += 1
        b["wins"] += outcome(p) == "WIN"
    return [{"period_start": k, **v} for k, v in sorted(buckets.items())]


def _consistency(values: list[Decimal]) -> tuple[Decimal | None, Decimal | None]:
    if not values:
        return None, None
    pct = Decimal(sum(1 for v in values if v > 0)) / len(values) * 100
    std = Decimal(str(statistics.pstdev([float(v) for v in values]))) if len(values) > 1 else ZERO
    return pct, std


def summary(rows: Sequence[PositionRow], tz: ZoneInfo, week_start: str = "MONDAY",
            starting_balance: Decimal | None = None) -> dict:
    n = len(rows)
    wins = [p for p in rows if outcome(p) == "WIN"]
    losses = [p for p in rows if outcome(p) == "LOSS"]
    gross_profit = sum((p.net for p in wins), ZERO)
    gross_loss = -sum((p.net for p in losses), ZERO)
    net = sum((p.net for p in rows), ZERO)
    pf, pf_inf = profit_factor(gross_profit, gross_loss)
    max_w, max_l = streaks(rows)
    days = daily_pnl(rows, tz)
    weeks = period_pnl(rows, tz, "week", week_start)
    sessions: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in rows:
        sessions[p.session] += p.net
    rr = [v for v in map(pips.planned_rr, rows) if v is not None]
    rm = [v for v in map(pips.r_multiple, rows) if v is not None]
    tp_pips = [v for v in map(pips.planned_tp_pips, rows) if v is not None]
    sl_pips = [v for v in map(pips.planned_sl_pips, rows) if v is not None]
    win_exit = [v for v in map(pips.actual_exit_pips, wins) if v is not None]
    loss_exit = [v for v in map(pips.actual_exit_pips, losses) if v is not None]
    daily_pct, daily_std = _consistency([d["net"] for d in days])
    weekly_pct, _ = _consistency([w["net"] for w in weeks])
    holding = [(p.close_time - p.open_time).total_seconds() for p in rows]
    best_day = max(days, key=lambda d: d["net"]) if days else None
    worst_day = min(days, key=lambda d: d["net"]) if days else None
    return {
        "trade_count": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": n - len(wins) - len(losses),
        "net_profit": net,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "total_commission": sum((p.commission for p in rows), ZERO),
        "total_swap": sum((p.swap for p in rows), ZERO),
        "total_fees": sum((p.fees for p in rows), ZERO),
        "win_rate": Decimal(len(wins)) / n * 100 if n else None,
        "avg_win": gross_profit / len(wins) if wins else None,
        "avg_loss": gross_loss / len(losses) if losses else None,
        "profit_factor": pf,
        "profit_factor_infinite": pf_inf,
        "expectancy": net / n if n else None,
        "largest_win": max((p.net for p in wins), default=None),
        "largest_loss": min((p.net for p in losses), default=None),
        **drawdown(rows, starting_balance),
        "avg_holding_seconds": sum(holding) / n if n else None,
        "best_day": {"date": best_day["date"], "net": best_day["net"]} if best_day else None,
        "worst_day": {"date": worst_day["date"], "net": worst_day["net"]} if worst_day else None,
        "best_session": max(sessions.items(), key=lambda kv: kv[1])[0] if sessions else None,
        "worst_session": min(sessions.items(), key=lambda kv: kv[1])[0] if sessions else None,
        "max_consecutive_wins": max_w,
        "max_consecutive_losses": max_l,
        "avg_planned_rr": _mean(rr),
        "planned_rr_count": len(rr),
        "avg_r_multiple": _mean(rm),
        "r_multiple_count": len(rm),
        "avg_planned_tp_pips": _mean(tp_pips),
        "planned_tp_count": len(tp_pips),
        "avg_planned_sl_pips": _mean(sl_pips),
        "planned_sl_count": len(sl_pips),
        "avg_win_exit_pips": _mean(win_exit),
        "avg_loss_exit_pips": _mean(loss_exit),
        "trading_days": len(days),
        "daily_win_pct": daily_pct,
        "daily_net_std": daily_std,
        "weekly_win_pct": weekly_pct,
        "long_count": sum(1 for p in rows if p.direction == "BUY"),
        "short_count": sum(1 for p in rows if p.direction == "SELL"),
    }


def breakdown(rows: Iterable[PositionRow], key: Callable[[PositionRow], str | None]) -> list[dict]:
    groups: dict[str, list[PositionRow]] = defaultdict(list)
    for p in rows:
        groups[key(p) or "Unspecified"].append(p)
    out = []
    for name, items in groups.items():
        wins = [p for p in items if outcome(p) == "WIN"]
        losses = [p for p in items if outcome(p) == "LOSS"]
        gp = sum((p.net for p in wins), ZERO)
        gl = -sum((p.net for p in losses), ZERO)
        pf, inf = profit_factor(gp, gl)
        net = sum((p.net for p in items), ZERO)
        rm = [v for v in map(pips.r_multiple, items) if v is not None]
        out.append({
            "key": name, "trades": len(items), "wins": len(wins), "losses": len(losses),
            "net_profit": net, "gross_profit": gp, "gross_loss": gl,
            "win_rate": Decimal(len(wins)) / len(items) * 100,
            "profit_factor": pf, "profit_factor_infinite": inf,
            "expectancy": net / len(items), "avg_r_multiple": _mean(rm),
            "avg_holding_seconds": sum((p.close_time - p.open_time).total_seconds()
                                       for p in items) / len(items),
        })
    return sorted(out, key=lambda r: r["net_profit"], reverse=True)


def equity_curve(rows: Sequence[PositionRow], cash_flows: Sequence[CashFlow] = (),
                 starting_balance: Decimal | None = None) -> list[dict]:
    """Realized P/L curve (always) and balance series (only when balance data exists)."""
    has_balance = starting_balance is not None or bool(cash_flows)
    flows = sorted(cash_flows, key=lambda c: c.time)
    balance = starting_balance or ZERO
    fi = 0
    cum = peak = ZERO
    points = []
    for p in by_close(rows):
        while fi < len(flows) and flows[fi].time <= p.close_time:
            balance += flows[fi].amount
            fi += 1
        cum += p.net
        balance += p.net
        peak = max(peak, cum)
        points.append({"time": p.close_time, "position_id": p.id, "net": p.net,
                       "cumulative": cum, "drawdown": cum - peak,
                       "balance": balance if has_balance else None})
    return points


def histogram(values: Sequence[Decimal], bins: int = 20) -> list[dict]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [{"from": lo, "to": hi, "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - lo) / width), bins - 1)] += 1
    return [{"from": lo + width * i, "to": lo + width * (i + 1), "count": c}
            for i, c in enumerate(counts)]


def hour_weekday_breakdowns(rows: Sequence[PositionRow], tz: ZoneInfo) -> dict:
    return {
        "entry_hour": breakdown(rows, lambda p: f"{p.open_time.astimezone(tz).hour:02d}:00"),
        "weekday": breakdown(rows, lambda p: WEEKDAYS[local_day(p.close_time, tz).weekday()]),
    }
