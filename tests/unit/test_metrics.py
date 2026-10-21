from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from app.services.analytics import metrics, pips
from app.services.analytics.types import CashFlow, PositionRow

JKT = ZoneInfo("Asia/Jakarta")
T0 = datetime(2026, 1, 5, 2, 0, tzinfo=UTC)  # Monday 09:00 Jakarta


def pos(i, net, *, hours=1, close_offset_h=None, direction="BUY", symbol="EURUSD",
        open_price="1.1000", close_price=None, sl=None, tp=None, source="OPEN_ORDER",
        pip="0.0001", volume="1", commission="0", swap="0", session="LONDON", gross=None,
        currency="USD", **kw):
    open_t = T0 + timedelta(hours=(close_offset_h if close_offset_h is not None else i * 24))
    net = D(str(net))
    commission, swap = D(commission), D(swap)
    return PositionRow(
        id=i, account_id=1, external_position_id=str(i), symbol=symbol, direction=direction,
        volume=D(volume), open_time=open_t, close_time=open_t + timedelta(hours=hours),
        open_price=D(open_price), close_price=D(close_price) if close_price else None,
        gross=D(str(gross)) if gross is not None else net - commission - swap,
        commission=commission, swap=swap, fees=D(0), net=net, currency=currency,
        sl=D(sl) if sl else None, tp=D(tp) if tp else None, sl_tp_source=source,
        session=session, pip_size=D(pip) if pip else None, **kw)


def test_core_metrics_mixed():
    rows = [pos(1, 100), pos(2, -50), pos(3, 0), pos(4, 200), pos(5, -25)]
    s = metrics.summary(rows, JKT)
    assert (s["trade_count"], s["wins"], s["losses"], s["breakevens"]) == (5, 2, 2, 1)
    assert s["net_profit"] == D(225)
    assert s["gross_profit"] == D(300) and s["gross_loss"] == D(75)
    assert s["win_rate"] == D(40)  # breakeven stays in denominator
    assert s["avg_win"] == D(150) and s["avg_loss"] == D("37.5")
    assert s["profit_factor"] == D(4) and not s["profit_factor_infinite"]
    assert s["expectancy"] == D(45)
    assert s["largest_win"] == D(200) and s["largest_loss"] == D(-50)
    wr, lr = s["wins"] / 5, s["losses"] / 5
    assert D(str(wr)) * s["avg_win"] - D(str(lr)) * s["avg_loss"] == s["expectancy"]


def test_no_trades():
    s = metrics.summary([], JKT)
    assert s["trade_count"] == 0 and s["win_rate"] is None and s["expectancy"] is None
    assert s["profit_factor"] is None and not s["profit_factor_infinite"]
    assert s["best_day"] is None and s["avg_planned_rr"] is None


def test_no_losing_trades_profit_factor_infinite():
    s = metrics.summary([pos(1, 10), pos(2, 5)], JKT)
    assert s["profit_factor"] is None and s["profit_factor_infinite"]
    assert s["avg_loss"] is None and s["gross_loss"] == 0 and s["max_drawdown"] == 0


def test_no_winning_trades():
    s = metrics.summary([pos(1, -10), pos(2, -5)], JKT)
    assert s["profit_factor"] == 0 and s["win_rate"] == 0 and s["avg_win"] is None
    assert s["max_drawdown"] == D(15) and s["max_consecutive_losses"] == 2


def test_only_breakevens():
    s = metrics.summary([pos(1, 0), pos(2, "0.004")], JKT)  # rounds to 0.00
    assert s["breakevens"] == 2 and s["win_rate"] == 0
    assert s["profit_factor"] is None and not s["profit_factor_infinite"]


def test_costs_are_part_of_net_once():
    p = pos(1, "92.60", commission="-7.00", swap="-0.40")
    assert p.gross == D("100.00")
    s = metrics.summary([p], JKT)
    assert s["net_profit"] == D("92.60")
    assert s["total_commission"] == D("-7.00") and s["total_swap"] == D("-0.40")


def test_commission_turns_gross_win_into_loss():
    p = pos(1, "-2.00", commission="-7.00")  # gross +5, net -2
    assert metrics.outcome(p) == "LOSS"


def test_streaks_breakeven_breaks_both():
    rows = [pos(1, 1), pos(2, 1), pos(3, 0), pos(4, 1), pos(5, -1), pos(6, -1), pos(7, -1)]
    assert metrics.streaks(rows) == (2, 3)


def test_drawdown_absolute_and_pct():
    rows = [pos(1, 100), pos(2, -150), pos(3, 50), pos(4, -20)]
    dd = metrics.drawdown(rows, starting_balance=D(1000))
    assert dd["max_drawdown"] == D(150)
    assert dd["max_drawdown_pct"].quantize(D("0.01")) == D("13.64")  # 150 / 1100
    assert metrics.drawdown(rows)["max_drawdown_pct"] is None


def test_timezone_attribution_and_crossing_midnight():
    # Opens 23:30 Jakarta (16:30 UTC) and closes 00:30 next day Jakarta.
    p = PositionRow(id=1, account_id=1, external_position_id="1", symbol="EURUSD",
                    direction="BUY", volume=D(1), open_time=datetime(2026, 1, 5, 16, 30, tzinfo=UTC),
                    close_time=datetime(2026, 1, 5, 17, 30, tzinfo=UTC), open_price=D(1),
                    close_price=D(1), gross=D(5), commission=D(0), swap=D(0), fees=D(0), net=D(5))
    assert metrics.daily_pnl([p], JKT)[0]["date"] == date(2026, 1, 6)
    assert metrics.daily_pnl([p], ZoneInfo("UTC"))[0]["date"] == date(2026, 1, 5)


def test_weekly_aggregation_monday_and_sunday_start():
    rows = [pos(0, 10), pos(6, 20), pos(7, 30)]  # Mon 5th, Sun 11th, Mon 12th (Jakarta)
    weeks = metrics.period_pnl(rows, JKT, "week", "MONDAY")
    assert [(w["period_start"], w["net"]) for w in weeks] == [
        (date(2026, 1, 5), D(30)), (date(2026, 1, 12), D(30))]
    sunday = metrics.period_pnl(rows, JKT, "week", "SUNDAY")
    assert [w["period_start"] for w in sunday] == [date(2026, 1, 4), date(2026, 1, 11)]
    months = metrics.period_pnl(rows, JKT, "month")
    assert months[0]["period_start"] == date(2026, 1, 1) and months[0]["trades"] == 3


def test_daily_consistency_and_best_worst_day():
    rows = [pos(1, 10), pos(2, -5), pos(3, 20), pos(4, 0)]
    s = metrics.summary(rows, JKT)
    assert s["trading_days"] == 4 and s["daily_win_pct"] == D(50)
    assert s["best_day"]["net"] == D(20) and s["worst_day"]["net"] == D(-5)


def test_best_worst_session():
    rows = [pos(1, 10, session="ASIA"), pos(2, -30, session="LONDON"),
            pos(3, 25, session="NEW_YORK")]
    s = metrics.summary(rows, JKT)
    assert s["best_session"] == "NEW_YORK" and s["worst_session"] == "LONDON"


def test_fx_pips_rr_and_r_multiple_buy_and_sell():
    buy = pos(1, "200", open_price="1.1000", close_price="1.1020", sl="1.0990", tp="1.1030",
              gross="200")
    sell = pos(2, "-100", direction="SELL", open_price="1.2000", close_price="1.2010",
               sl="1.2010", tp="1.1970", gross="-100")
    assert pips.planned_sl_pips(buy) == D(10) and pips.planned_tp_pips(buy) == D(30)
    assert pips.actual_exit_pips(buy) == D(20) and pips.planned_rr(buy) == D(3)
    assert pips.r_multiple(buy) == D(2)  # 200 / (10 pips * $10)
    assert pips.planned_sl_pips(sell) == D(10) and pips.actual_exit_pips(sell) == D(-10)
    assert pips.r_multiple(sell) == D(-1)
    s = metrics.summary([buy, sell], JKT)
    assert s["avg_planned_rr"] == D(3) and s["r_multiple_count"] == 2
    assert s["avg_win_exit_pips"] == D(20) and s["avg_loss_exit_pips"] == D(-10)


def test_jpy_and_gold_pip_sizes():
    jpy = pos(1, "50", symbol="USDJPY", open_price="150.00", close_price="150.25",
              sl="149.90", pip="0.01")
    gold = pos(2, "500", symbol="XAUUSD", open_price="2350.00", close_price="2355.00",
               sl="2347.00", pip="0.1", volume="1")
    assert pips.actual_exit_pips(jpy) == D(25) and pips.planned_sl_pips(jpy) == D(10)
    assert pips.actual_exit_pips(gold) == D(50) and pips.planned_sl_pips(gold) == D(30)


def test_missing_sl_tp_is_unavailable_not_imputed():
    p = pos(1, 10, close_price="1.1010")
    assert pips.planned_rr(p) is None and pips.r_multiple(p) is None
    assert pips.planned_sl_pips(p) is None and pips.actual_exit_pips(p) == D(10)
    s = metrics.summary([p], JKT)
    assert s["avg_planned_rr"] is None and s["planned_rr_count"] == 0


def test_mt4_last_known_sl_not_used_as_initial_risk():
    p = pos(1, 10, close_price="1.1010", sl="1.0990", source="LAST_KNOWN")
    assert pips.initial_sl(p) is None and pips.r_multiple(p) is None


def test_unknown_pip_size():
    p = pos(1, 10, close_price="1.1010", pip=None)
    assert pips.actual_exit_pips(p) is None


def test_r_multiple_uses_tick_value_when_available():
    p = pos(1, "-50", close_price="1.1000", sl="1.0950", tick_size=D("0.00001"),
            tick_value=D("1"), gross="0", commission="-50")
    # breakeven price exit: value per price unit from tick data = 100000 per lot
    assert pips.r_multiple(p) == D("-0.1")


def test_breakdown_and_histogram_and_equity_curve():
    rows = [pos(1, 10, symbol="EURUSD"), pos(2, -5, symbol="EURUSD"), pos(3, 7, symbol="XAUUSD")]
    b = {r["key"]: r for r in metrics.breakdown(rows, lambda p: p.symbol)}
    assert b["EURUSD"]["trades"] == 2 and b["EURUSD"]["win_rate"] == D(50)
    assert b["XAUUSD"]["profit_factor_infinite"]
    h = metrics.histogram([r.net for r in rows], bins=3)
    assert sum(x["count"] for x in h) == 3
    curve = metrics.equity_curve(rows, [CashFlow(T0 + timedelta(days=2), D(100), "USD")],
                                 starting_balance=D(1000))
    assert [c["cumulative"] for c in curve] == [D(10), D(5), D(12)]
    assert [c["balance"] for c in curve] == [D(1010), D(1105), D(1112)]  # deposit lands before trade 2 closes
    assert curve[1]["drawdown"] == D(-5)
    assert metrics.equity_curve(rows)[0]["balance"] is None


@pytest.mark.parametrize("week_start,expected", [("MONDAY", date(2026, 1, 5)),
                                                 ("SUNDAY", date(2026, 1, 4))])
def test_week_start_of(week_start, expected):
    assert metrics.week_start_of(date(2026, 1, 7), week_start) == expected
