"""Trading-session attribution by position open time (see docs/analytics-definitions.md)."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

OFF_SESSION = "OFF_SESSION"


@dataclass(frozen=True)
class SessionDef:
    name: str
    tz: ZoneInfo
    start: time
    end: time


@lru_cache
def parse_sessions(spec: str) -> tuple[SessionDef, ...]:
    """Parse ``NAME=Area/City,HH:MM,HH:MM;...``."""
    out = []
    for part in filter(None, (p.strip() for p in spec.split(";"))):
        name, _, rest = part.partition("=")
        tz, start, end = (x.strip() for x in rest.split(","))
        out.append(SessionDef(name.strip().upper(), ZoneInfo(tz),
                              time.fromisoformat(start), time.fromisoformat(end)))
    return tuple(out)


def _opened_at(dt_utc: datetime, s: SessionDef) -> datetime | None:
    local = dt_utc.astimezone(s.tz)
    t = local.time()
    if s.start <= s.end:
        if not (s.start <= t < s.end):
            return None
        day = local.date()
    else:  # wraps midnight
        if s.end <= t < s.start:
            return None
        day = local.date() if t >= s.start else local.date() - timedelta(days=1)
    return datetime.combine(day, s.start, tzinfo=s.tz).astimezone(UTC)


def session_for(dt_utc: datetime, spec: str) -> str:
    """Session containing ``dt_utc``; overlaps go to the most recently opened session."""
    best: tuple[datetime, str] | None = None
    for s in parse_sessions(spec):
        opened = _opened_at(dt_utc, s)
        if opened is not None and (best is None or opened > best[0]):
            best = (opened, s.name)
    return best[1] if best else OFF_SESSION
