from datetime import UTC, datetime

from sqlalchemy import DateTime, Numeric
from sqlalchemy.types import TypeDecorator

Money = Numeric(18, 2)
Price = Numeric(20, 10)
Volume = Numeric(14, 4)


class UTCDateTime(TypeDecorator):
    """Timezone-aware datetime stored as UTC; SQLite gets naive UTC values."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use UTC-aware values.")
        value = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
