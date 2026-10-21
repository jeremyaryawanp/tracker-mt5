from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, enum_col, utcnow
from app.models.enums import SyncSource, SyncStatus
from app.models.types import UTCDateTime


class SyncRun(TimestampMixin, Base):
    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("trading_account.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[SyncSource] = mapped_column(enum_col(SyncSource))
    status: Mapped[SyncStatus] = mapped_column(enum_col(SyncStatus), default=SyncStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    range_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    range_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deals_received: Mapped[int] = mapped_column(Integer, default=0)
    deals_inserted: Mapped[int] = mapped_column(Integer, default=0)
    deals_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    deals_updated: Mapped[int] = mapped_column(Integer, default=0)
    positions_rebuilt: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("sync_run.id", ondelete="SET NULL"))
    failed_payload: Mapped[dict | None] = mapped_column(JSON)
