"""Manual journal data (annotations, tags), trade listing and CSV export."""

import csv
import io
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag, TradeAnnotation, TradePosition, TradingAccount, User
from app.models.enums import TagKind
from app.services.analytics import metrics, pips
from app.services.analytics.service import Analytics
from app.services.analytics.types import AnalyticsFilter, PositionRow

TEXT_FIELDS = ("setup_name", "trading_session_override", "market_condition", "entry_timeframe",
               "higher_timeframe_context", "entry_reason", "exit_reason", "emotional_state",
               "screenshot_ref", "personal_notes")
TAG_FIELDS = {"mistakes": TagKind.MISTAKE, "ict_tags": TagKind.ICT,
              "setup_tags": TagKind.SETUP, "custom_tags": TagKind.CUSTOM}
SORTS = {"close_time": lambda r: r.close_time, "net": lambda r: r.net,
         "symbol": lambda r: r.symbol, "volume": lambda r: r.volume}


def get_position(session: Session, user: User, position_id: int) -> TradePosition | None:
    return session.scalar(select(TradePosition).join(TradingAccount).where(
        TradePosition.id == position_id, TradingAccount.user_id == user.id))


def get_or_create_tag(session: Session, user: User, kind: TagKind, name: str) -> Tag:
    name = name.strip()[:80]
    tag = session.scalar(select(Tag).where(Tag.user_id == user.id, Tag.kind == kind,
                                           Tag.name == name))
    if tag is None:
        tag = Tag(user_id=user.id, kind=kind, name=name)
        session.add(tag)
        session.flush()
    return tag


def list_tags(session: Session, user: User) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in TAG_FIELDS}
    kinds = {v: k for k, v in TAG_FIELDS.items()}
    for t in session.scalars(select(Tag).where(Tag.user_id == user.id).order_by(Tag.name)):
        out[kinds[t.kind]].append(t.name)
    return out


def upsert_annotation(session: Session, user: User, position: TradePosition,
                      data: dict) -> TradeAnnotation:
    ann = position.annotation or TradeAnnotation(trade_position_id=position.id)
    if position.annotation is None:
        session.add(ann)
        position.annotation = ann
    for f in TEXT_FIELDS:
        if f in data:
            v = data[f]
            ann.__setattr__(f, (v.strip() or None) if isinstance(v, str) else v)
    if "rule_followed" in data:
        ann.rule_followed = data["rule_followed"]
    if any(k in data for k in TAG_FIELDS):
        keep = [t for t in ann.tags if not any(k in data and t.kind == kind
                                               for k, kind in TAG_FIELDS.items())]
        for key, kind in TAG_FIELDS.items():
            if key in data:
                names = dict.fromkeys(n.strip() for n in data[key] or [] if n and n.strip())
                keep += [get_or_create_tag(session, user, kind, n) for n in names]
        ann.tags = keep
    session.flush()
    return ann


def apply_simulated_annotations(session: Session, account: TradingAccount, data: dict) -> None:
    user = session.get(User, account.user_id)
    positions = session.scalars(select(TradePosition).where(
        TradePosition.account_id == account.id,
        TradePosition.external_position_id.in_(list(data))))
    for p in positions:
        if p.annotation is None:  # never overwrite user edits
            upsert_annotation(session, user, p, data[p.external_position_id])


def search_rows(rows: list[PositionRow], q: str | None) -> list[PositionRow]:
    if not q:
        return rows
    q = q.lower().strip()
    return [r for r in rows if q in r.symbol.lower() or q in r.external_position_id.lower()
            or q in (r.setup or "").lower() or any(q in t.lower() for t in r.tags + r.mistakes)]


def list_trades(session: Session, user: User, f: AnalyticsFilter, *, q: str | None = None,
                page: int = 1, page_size: int = 25, sort: str = "close_time",
                desc: bool = True) -> tuple[list[PositionRow], int]:
    rows = search_rows(Analytics(session, user).rows(f), q)
    rows.sort(key=SORTS.get(sort, SORTS["close_time"]), reverse=desc)
    page = max(page, 1)
    return rows[(page - 1) * page_size: page * page_size], len(rows)


CSV_COLUMNS = ["position_id", "account_id", "symbol", "direction", "volume", "open_time_utc",
               "close_time_utc", "open_price", "close_price", "initial_sl", "initial_tp",
               "sl_tp_source", "gross_profit", "commission", "swap", "fees", "net_profit",
               "currency", "outcome", "session", "exit_count", "pips", "r_multiple", "setup",
               "rule_followed", "emotional_state", "tags", "mistakes", "simulated"]


def _cell(v) -> str:
    s = "" if v is None else (v.isoformat() if isinstance(v, datetime) else str(v))
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not _numeric(s) else s


def _numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def export_csv(rows: list[PositionRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for r in rows:
        w.writerow([_cell(v) for v in (
            r.external_position_id, r.account_id, r.symbol, r.direction, r.volume, r.open_time,
            r.close_time, r.open_price, r.close_price, pips.initial_sl(r), pips.initial_tp(r),
            r.sl_tp_source, r.gross, r.commission, r.swap, r.fees, r.net, r.currency,
            metrics.outcome(r), r.session, r.exit_count, pips.actual_exit_pips(r),
            pips.r_multiple(r), r.setup, r.rule_followed, r.emotional_state, "|".join(r.tags),
            "|".join(r.mistakes), r.is_simulated)])
    return buf.getvalue()
