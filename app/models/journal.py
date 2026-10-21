from datetime import date

from sqlalchemy import (
    JSON,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, enum_col
from app.models.enums import ReviewPeriod, TagKind
from app.models.trade import TradePosition

annotation_tag = Table(
    "annotation_tag",
    Base.metadata,
    Column(
        "annotation_id",
        Integer,
        ForeignKey("trade_annotation.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", Integer, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(TimestampMixin, Base):
    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("user_id", "kind", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[TagKind] = mapped_column(enum_col(TagKind))


class TradeAnnotation(TimestampMixin, Base):
    """User-owned journal data; never modified by synchronization."""

    __tablename__ = "trade_annotation"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_position_id: Mapped[int] = mapped_column(
        ForeignKey("trade_position.id", ondelete="CASCADE"), unique=True
    )
    setup_name: Mapped[str | None] = mapped_column(String(120))
    trading_session_override: Mapped[str | None] = mapped_column(String(20))
    market_condition: Mapped[str | None] = mapped_column(String(80))
    entry_timeframe: Mapped[str | None] = mapped_column(String(20))
    higher_timeframe_context: Mapped[str | None] = mapped_column(String(255))
    entry_reason: Mapped[str | None] = mapped_column(Text)
    exit_reason: Mapped[str | None] = mapped_column(Text)
    rule_followed: Mapped[bool | None] = mapped_column()
    emotional_state: Mapped[str | None] = mapped_column(String(80))
    screenshot_ref: Mapped[str | None] = mapped_column(String(500))
    personal_notes: Mapped[str | None] = mapped_column(Text)

    position: Mapped[TradePosition] = relationship(back_populates="annotation")
    tags: Mapped[list[Tag]] = relationship(secondary=annotation_tag, lazy="selectin")


class TradeReview(TimestampMixin, Base):
    __tablename__ = "trade_review"
    __table_args__ = (UniqueConstraint("user_id", "account_id", "review_period", "period_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("trading_account.id", ondelete="CASCADE")
    )
    review_period: Mapped[ReviewPeriod] = mapped_column(enum_col(ReviewPeriod))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64))
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSON)
    performance_summary: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[str | None] = mapped_column(Text)
    mistakes: Mapped[str | None] = mapped_column(Text)
    repeated_mistakes: Mapped[str | None] = mapped_column(Text)
    lessons_learned: Mapped[str | None] = mapped_column(Text)
    improvement_plan: Mapped[str | None] = mapped_column(Text)
    stop_doing: Mapped[str | None] = mapped_column(Text)
    continue_doing: Mapped[str | None] = mapped_column(Text)
    next_week_goals: Mapped[str | None] = mapped_column(Text)
    auto_summary: Mapped[str | None] = mapped_column(Text)
    llm_summary: Mapped[str | None] = mapped_column(Text)



