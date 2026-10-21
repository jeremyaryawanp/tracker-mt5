"""Month calendar of realized P/L by close day in the display timezone."""

import calendar as pycal
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.analytics import metrics
from app.services.analytics.types import PositionRow

ZERO = Decimal("0")


def parse_month(value: str | None, today: date) -> date:
    try:
        y, m = (int(x) for x in (value or "").split("-"))
        return date(y, m, 1)
    except (ValueError, TypeError):
        return today.replace(day=1)


def shift_month(first: date, delta: int) -> date:
    idx = first.year * 12 + first.month - 1 + delta
    return date(idx // 12, idx % 12 + 1, 1)


def month_grid(rows: list[PositionRow], tz: ZoneInfo, first: date,
               week_start: str = "MONDAY") -> dict:
    last = first.replace(day=pycal.monthrange(first.year, first.month)[1])
    days = {d["date"]: d for d in metrics.daily_pnl(rows, tz)}
    start = metrics.week_start_of(first, week_start)
    weeks = []
    cur = start
    while cur <= last:
        cells = []
        for i in range(7):
            d = cur + timedelta(days=i)
            info = days.get(d) if d.month == first.month else None
            cells.append({"date": d, "in_month": d.month == first.month,
                          "net": info["net"] if info else None,
                          "trades": info["trades"] if info else 0,
                          "wins": info["wins"] if info else 0,
                          "losses": info["losses"] if info else 0})
        in_month = [c for c in cells if c["in_month"] and c["trades"]]
        weeks.append({"start": cur, "days": cells,
                      "net": sum((c["net"] for c in in_month), ZERO),
                      "trades": sum(c["trades"] for c in in_month)})
        cur += timedelta(days=7)
    month_days = [d for k, d in days.items() if first <= k <= last]
    return {
        "month": first, "weeks": weeks,
        "weekday_names": [metrics.WEEKDAYS[(metrics.WEEKDAYS.index(week_start.upper()) + i)
                                           % 7][:3].title() for i in range(7)],
        "net": sum((d["net"] for d in month_days), ZERO),
        "trades": sum(d["trades"] for d in month_days),
        "green_days": sum(1 for d in month_days if d["net"] > 0),
        "red_days": sum(1 for d in month_days if d["net"] < 0),
    }


def rows_on_day(rows: list[PositionRow], tz: ZoneInfo, day: date) -> list[PositionRow]:
    return [r for r in metrics.by_close(rows) if metrics.local_day(r.close_time, tz) == day]
