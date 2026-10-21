from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.services.analytics.types import AnalyticsFilter


def current_user(db: Session, settings: Settings, sess) -> User | None:
    if settings.auth_enabled:
        uid = sess.get("user_id") if sess is not None else None
        return db.get(User, uid) if uid else None
    return db.scalar(select(User).where(User.username == settings.admin_username))


def _d(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def filter_from_query(q) -> AnalyticsFilter:
    def many(k):
        return [v for v in q.getlist(k) if v] if hasattr(q, "getlist") else []
    acc = [int(a) for a in many("account_id") if a.isdigit()]
    outcome = q.get("outcome") if q.get("outcome") in ("WIN", "LOSS", "BREAKEVEN") else None
    return AnalyticsFilter(acc or None, _d(q.get("date_from")), _d(q.get("date_to")),
                           many("symbol"), [d.upper() for d in many("direction")],
                           many("session"), many("setup"), many("tag"), outcome)
