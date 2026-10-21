from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.types import UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


def enum_col(enum_cls: type[StrEnum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=20, validate_strings=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
