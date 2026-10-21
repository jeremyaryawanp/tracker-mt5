from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import User
from app.services.analytics import metrics
from app.services.analytics.service import Analytics
from app.services.analytics.types import AnalyticsFilter

router = APIRouter(prefix="/analytics", tags=["analytics"])
BREAKDOWNS = {
    "symbol": lambda p: p.symbol,
    "session": lambda p: p.session,
    "direction": lambda p: p.direction,
    "setup": lambda p: p.setup,
    "emotion": lambda p: p.emotional_state,
    "rule_followed": lambda p: {True: "Followed", False: "Broken"}.get(p.rule_followed),
}


def get_filter(
    account_id: list[int] | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
    symbol: list[str] = Query(default=[]),
    direction: list[str] = Query(default=[]),
    session: list[str] = Query(default=[]),
    setup: list[str] = Query(default=[]),
    tag: list[str] = Query(default=[]),
    outcome: str | None = Query(default=None, pattern="^(WIN|LOSS|BREAKEVEN)$"),
) -> AnalyticsFilter:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    return AnalyticsFilter(account_id, date_from, date_to, symbol, [d.upper() for d in direction],
                           session, setup, tag, outcome)


def _svc(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Analytics:
    return Analytics(db, user)


@router.get("/summary")
def summary(f: AnalyticsFilter = Depends(get_filter), svc: Analytics = Depends(_svc)):
    return jsonable_encoder({"timezone": str(svc.tz), "by_currency": svc.summary(f)})


@router.get("/equity")
def equity(f: AnalyticsFilter = Depends(get_filter), svc: Analytics = Depends(_svc)):
    return jsonable_encoder(svc.equity(f))


@router.get("/daily")
def daily(f: AnalyticsFilter = Depends(get_filter), svc: Analytics = Depends(_svc)):
    return jsonable_encoder({c: metrics.daily_pnl(rows, svc.tz)
                             for c, rows in svc.by_currency(svc.rows(f)).items()})


@router.get("/periods")
def periods(period: str = Query(default="week", pattern="^(week|month)$"),
            f: AnalyticsFilter = Depends(get_filter), svc: Analytics = Depends(_svc)):
    return jsonable_encoder({c: metrics.period_pnl(rows, svc.tz, period, svc.week_start)
                             for c, rows in svc.by_currency(svc.rows(f)).items()})


@router.get("/breakdown")
def breakdown(by: str = Query(pattern="^(symbol|session|direction|setup|emotion|rule_followed|"
                                      "entry_hour|weekday)$"),
              f: AnalyticsFilter = Depends(get_filter), svc: Analytics = Depends(_svc)):
    out = {}
    for currency, rows in svc.by_currency(svc.rows(f)).items():
        if by in BREAKDOWNS:
            out[currency] = metrics.breakdown(rows, BREAKDOWNS[by])
        else:
            out[currency] = metrics.hour_weekday_breakdowns(rows, svc.tz)[by]
    return jsonable_encoder(out)
