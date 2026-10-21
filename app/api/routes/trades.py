from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.api.routes.analytics import get_filter
from app.models import User
from app.schemas.journal import AnnotationIn
from app.services import journal
from app.services.analytics import metrics, pips
from app.services.analytics.service import Analytics
from app.services.analytics.types import AnalyticsFilter

router = APIRouter(tags=["journal"])


def _row_json(r):
    return {**jsonable_encoder(r.__dict__), "outcome": metrics.outcome(r),
            "pips": pips.actual_exit_pips(r), "r_multiple": pips.r_multiple(r)}


@router.get("/trades")
def trades(f: AnalyticsFilter = Depends(get_filter), q: str | None = Query(None, max_length=80),
           page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
           sort: str = Query("close_time", pattern="^(close_time|net|symbol|volume)$"),
           order: str = Query("desc", pattern="^(asc|desc)$"),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows, total = journal.list_trades(db, user, f, q=q, page=page, page_size=page_size,
                                      sort=sort, desc=order == "desc")
    return jsonable_encoder({"total": total, "page": page, "page_size": page_size,
                             "items": [_row_json(r) for r in rows]})


@router.get("/trades/export.csv")
def export(f: AnalyticsFilter = Depends(get_filter), q: str | None = Query(None, max_length=80),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = journal.search_rows(Analytics(db, user).rows(f), q)
    return Response(journal.export_csv(rows), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="tradejournal-trades.csv"'})


@router.get("/trades/{position_id}")
def trade(position_id: int, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    p = journal.get_position(db, user, position_id)
    if p is None:
        raise HTTPException(404, "Trade not found")
    a = p.annotation
    return jsonable_encoder({
        "id": p.id, "account_id": p.account_id, "position_id": p.external_position_id,
        "symbol": p.symbol, "direction": p.direction, "status": p.status,
        "volume": p.volume_lots, "open_time": p.open_time, "close_time": p.close_time,
        "open_price": p.open_price, "close_price": p.close_price,
        "initial_sl": p.initial_sl_price, "initial_tp": p.initial_tp_price,
        "sl_tp_source": p.sl_tp_source, "net": p.realized_net_profit,
        "gross": p.realized_gross_profit, "commission": p.commission, "swap": p.swap,
        "fees": p.fees, "session": p.trading_session, "exit_count": p.exit_count,
        "annotation": None if a is None else {
            **{f: getattr(a, f) for f in journal.TEXT_FIELDS},
            "rule_followed": a.rule_followed,
            **{k: [t.name for t in a.tags if t.kind == kind]
               for k, kind in journal.TAG_FIELDS.items()}},
    })


@router.put("/trades/{position_id}/annotation")
def annotate(position_id: int, body: AnnotationIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    p = journal.get_position(db, user, position_id)
    if p is None:
        raise HTTPException(404, "Trade not found")
    journal.upsert_annotation(db, user, p, body.model_dump(exclude_unset=True))
    db.commit()
    return trade(position_id, user, db)


@router.get("/tags")
def tags(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return journal.list_tags(db, user)
