"""Weekly review: metrics vs previous week, discipline analysis, rule-based summary, reflections."""

from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TradeReview, User
from app.models.enums import ReviewPeriod
from app.services.analytics import metrics
from app.services.analytics.service import Analytics
from app.services.analytics.types import AnalyticsFilter, PositionRow

ZERO = Decimal("0")
REFLECTION_FIELDS = ("performance_summary", "strengths", "mistakes", "repeated_mistakes",
                     "lessons_learned", "improvement_plan", "stop_doing", "continue_doing",
                     "next_week_goals")
COMPARE = ("net_profit", "trade_count", "win_rate", "profit_factor", "expectancy",
           "avg_win", "avg_loss", "max_drawdown", "avg_r_multiple")


def week_bounds(day: date, week_start: str) -> tuple[date, date]:
    start = metrics.week_start_of(day, week_start)
    return start, start + timedelta(days=6)


def discipline(rows: list[PositionRow]) -> dict:
    groups = {"followed": [r for r in rows if r.rule_followed is True],
              "broken": [r for r in rows if r.rule_followed is False],
              "unknown": [r for r in rows if r.rule_followed is None]}
    out = {k: {"trades": len(v), "net": sum((r.net for r in v), ZERO),
               "win_rate": (Decimal(sum(1 for r in v if metrics.outcome(r) == "WIN")) / len(v)
                            * 100) if v else None} for k, v in groups.items()}
    rated = len(groups["followed"]) + len(groups["broken"])
    out["adherence_pct"] = (Decimal(len(groups["followed"])) / rated * 100) if rated else None
    mistakes: Counter[str] = Counter()
    cost: dict[str, Decimal] = {}
    for r in rows:
        for m in r.mistakes:
            mistakes[m] += 1
            cost[m] = cost.get(m, ZERO) + r.net
    out["mistakes"] = [{"name": m, "count": c, "net": cost[m]} for m, c in mistakes.most_common()]
    emotions: dict[str, list[PositionRow]] = {}
    for r in rows:
        emotions.setdefault(r.emotional_state or "Unspecified", []).append(r)
    out["emotions"] = [{"name": k, "trades": len(v), "net": sum((r.net for r in v), ZERO)}
                       for k, v in sorted(emotions.items())]
    return out


def build_review(session: Session, user: User, week_of: date,
                 account_ids: list[int] | None = None) -> dict:
    svc = Analytics(session, user)
    start, end = week_bounds(week_of, user.week_start)
    base = AnalyticsFilter(account_ids=account_ids)
    cur_rows = svc.rows(replace(base, date_from=start, date_to=end))
    prev_rows = svc.rows(replace(base, date_from=start - timedelta(days=7),
                                 date_to=start - timedelta(days=1)))
    currencies = sorted({r.currency for r in cur_rows + prev_rows}) or ["USD"]
    per_currency = {}
    for cur in currencies:
        c = [r for r in cur_rows if r.currency == cur]
        p = [r for r in prev_rows if r.currency == cur]
        cs, ps = metrics.summary(c, svc.tz, user.week_start), metrics.summary(p, svc.tz)
        disc, prev_disc = discipline(c), discipline(p)
        prev_names = {m["name"] for m in prev_disc["mistakes"]}
        repeated = [m for m in disc["mistakes"] if m["count"] >= 2 or m["name"] in prev_names]
        ordered = sorted(c, key=lambda r: r.net)
        per_currency[cur] = {
            "current": cs, "previous": ps,
            "delta": {k: (cs[k] - ps[k]) if cs[k] is not None and ps[k] is not None else None
                      for k in COMPARE},
            "discipline": disc, "repeated_mistakes": repeated,
            "daily": metrics.daily_pnl(c, svc.tz),
            "by_symbol": metrics.breakdown(c, lambda r: r.symbol),
            "by_session": metrics.breakdown(c, lambda r: r.session),
            "by_setup": metrics.breakdown(c, lambda r: r.setup),
            "best_trade": _trade(ordered[-1]) if ordered and ordered[-1].net > 0 else None,
            "worst_trade": _trade(ordered[0]) if ordered and ordered[0].net < 0 else None,
        }
    data = {"week_start": start, "week_end": end, "timezone": str(svc.tz),
            "by_currency": per_currency}
    data["auto_summary"] = rule_based_summary(data)
    return data


def _trade(r: PositionRow) -> dict:
    return {"id": r.id, "symbol": r.symbol, "direction": r.direction, "net": r.net,
            "setup": r.setup, "close_time": r.close_time}


def _fmt(v: Decimal | None, places: int = 2) -> str:
    return "n/a" if v is None else f"{v:,.{places}f}"


def rule_based_summary(data: dict) -> str:
    lines: list[str] = []
    for cur, d in data["by_currency"].items():
        s, p, disc = d["current"], d["previous"], d["discipline"]
        if s["trade_count"] == 0:
            lines.append(f"No closed trades this week ({cur}).")
            continue
        trend = ""
        if p["trade_count"]:
            diff = s["net_profit"] - p["net_profit"]
            trend = f" ({'up' if diff >= 0 else 'down'} {_fmt(abs(diff))} vs previous week)"
        lines.append(f"Net {_fmt(s['net_profit'])} {cur} from {s['trade_count']} trades{trend}; "
                     f"win rate {_fmt(s['win_rate'], 1)}%, profit factor "
                     f"{'∞' if s['profit_factor_infinite'] else _fmt(s['profit_factor'])}.")
        if d["by_symbol"]:
            best, worst = d["by_symbol"][0], d["by_symbol"][-1]
            lines.append(f"Best symbol: {best['key']} ({_fmt(best['net_profit'])}); "
                         f"weakest: {worst['key']} ({_fmt(worst['net_profit'])}).")
        if disc["adherence_pct"] is not None:
            f_, b_ = disc["followed"], disc["broken"]
            lines.append(f"Rules followed on {_fmt(disc['adherence_pct'], 0)}% of rated trades. "
                         f"Followed: {_fmt(f_['net'])} over {f_['trades']} trades; broken: "
                         f"{_fmt(b_['net'])} over {b_['trades']} trades.")
            if b_["trades"] and b_["net"] < 0:
                lines.append("Breaking rules cost money this week - prioritise the checklist.")
        if d["repeated_mistakes"]:
            names = ", ".join(f"{m['name']} x{m['count']}" for m in d["repeated_mistakes"][:3])
            lines.append(f"Repeated mistakes: {names}.")
        if s["max_consecutive_losses"] >= 3:
            lines.append(f"Losing streak of {s['max_consecutive_losses']} - consider a daily "
                         f"loss limit or a pause rule after consecutive losses.")
        if s["r_multiple_count"] < s["trade_count"]:
            lines.append(f"{s['trade_count'] - s['r_multiple_count']} trades had no initial SL "
                         f"recorded, so R-multiple could not be computed for them.")
    return "\n".join(lines)


def get_review(session: Session, user: User, start: date,
               account_id: int | None = None) -> TradeReview | None:
    return session.scalar(select(TradeReview).where(
        TradeReview.user_id == user.id, TradeReview.review_period == ReviewPeriod.WEEK,
        TradeReview.period_start == start,
        TradeReview.account_id.is_(None) if account_id is None
        else TradeReview.account_id == account_id))


def save_review(session: Session, user: User, data: dict, fields: dict,
                account_id: int | None = None) -> TradeReview:
    from fastapi.encoders import jsonable_encoder
    review = get_review(session, user, data["week_start"], account_id)
    if review is None:
        review = TradeReview(user_id=user.id, account_id=account_id,
                             review_period=ReviewPeriod.WEEK, period_start=data["week_start"],
                             period_end=data["week_end"], timezone=data["timezone"])
        session.add(review)
    for f in REFLECTION_FIELDS:
        if f in fields:
            setattr(review, f, (fields[f] or "").strip()[:20000] or None)
    if "llm_summary" in fields:
        review.llm_summary = fields["llm_summary"]
    review.auto_summary = data["auto_summary"]
    review.metrics_snapshot = jsonable_encoder(
        {c: d["current"] for c, d in data["by_currency"].items()})
    session.flush()
    return review
