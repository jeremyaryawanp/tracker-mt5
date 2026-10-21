from datetime import UTC, date, datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from app.services.analytics.types import PositionRow
from app.services.reporting.calendar import month_grid, parse_month, rows_on_day, shift_month

JKT = ZoneInfo("Asia/Jakarta")


def row(i, close_utc, net):
    return PositionRow(id=i, account_id=1, external_position_id=str(i), symbol="EURUSD",
                       direction="BUY", volume=D(1), open_time=close_utc, close_time=close_utc,
                       open_price=D(1), close_price=D(1), gross=D(net), commission=D(0),
                       swap=D(0), fees=D(0), net=D(net))


def test_month_grid_and_timezone_boundary():
    rows = [row(1, datetime(2026, 2, 28, 18, 0, tzinfo=UTC), 10),  # Mar 1 01:00 Jakarta
            row(2, datetime(2026, 3, 2, 3, 0, tzinfo=UTC), -4),
            row(3, datetime(2026, 3, 2, 4, 0, tzinfo=UTC), 1)]
    g = month_grid(rows, JKT, date(2026, 3, 1), "MONDAY")
    assert g["weekday_names"][0] == "Mon" and g["weeks"][0]["start"] == date(2026, 2, 23)
    cells = {c["date"]: c for w in g["weeks"] for c in w["days"]}
    assert cells[date(2026, 3, 1)]["net"] == D(10)
    assert cells[date(2026, 3, 2)]["trades"] == 2 and cells[date(2026, 3, 2)]["net"] == D(-3)
    assert g["net"] == D(7) and g["green_days"] == 1 and g["red_days"] == 1
    assert g["weeks"][0]["net"] == D(10) and g["weeks"][1]["net"] == D(-3)
    assert all(len(w["days"]) == 7 for w in g["weeks"])
    utc = month_grid(rows, ZoneInfo("UTC"), date(2026, 3, 1))
    assert utc["net"] == D(-3)  # trade 1 falls on Feb 28 in UTC
    assert [r.id for r in rows_on_day(rows, JKT, date(2026, 3, 2))] == [2, 3]


def test_sunday_week_start_and_month_helpers():
    g = month_grid([], JKT, date(2026, 3, 1), "SUNDAY")
    assert g["weekday_names"][0] == "Sun" and g["weeks"][0]["start"] == date(2026, 3, 1)
    assert shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert parse_month("bad", date(2026, 5, 9)) == date(2026, 5, 1)
