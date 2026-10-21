from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, enum_col
from app.models.enums import (
    DealEntry,
    DealType,
    Direction,
    PositionStatus,
    SlTpSource,
)
from app.models.types import Money, Price, UTCDateTime, Volume


class TradeDeal(TimestampMixin, Base):
    """Raw broker execution; source of truth for positions."""

    __tablename__ = "trade_deal"
    __table_args__ = (
        UniqueConstraint("account_id", "external_deal_id"),
        Index("ix_trade_deal_account_position", "account_id", "external_position_id"),
        Index("ix_trade_deal_account_time", "account_id", "time_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("trading_account.id", ondelete="CASCADE"))
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("sync_run.id", ondelete="SET NULL"))
    external_deal_id: Mapped[str] = mapped_column(String(64))
    external_order_id: Mapped[str | None] = mapped_column(String(64))
    external_position_id: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str | None] = mapped_column(String(40))
    deal_type: Mapped[DealType] = mapped_column(enum_col(DealType))
    entry: Mapped[DealEntry] = mapped_column(enum_col(DealEntry))
    time_server_raw: Mapped[str | None] = mapped_column(String(32))
    time_utc: Mapped[datetime] = mapped_column(UTCDateTime)
    price: Mapped[Decimal | None] = mapped_column(Price)
    volume: Mapped[Decimal | None] = mapped_column(Volume)
    profit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    commission: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    swap: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    fee: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    sl_price: Mapped[Decimal | None] = mapped_column(Price)
    tp_price: Mapped[Decimal | None] = mapped_column(Price)
    magic: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(String(40))
    raw_payload: Mapped[dict | None] = mapped_column(JSON)


class TradeOrder(TimestampMixin, Base):
    """Broker order history; used for the initial SL/TP of a position."""

    __tablename__ = "trade_order"
    __table_args__ = (
        UniqueConstraint("account_id", "external_order_id"),
        Index("ix_trade_order_account_position", "account_id", "external_position_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("trading_account.id", ondelete="CASCADE"))
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("sync_run.id", ondelete="SET NULL"))
    external_order_id: Mapped[str] = mapped_column(String(64))
    external_position_id: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str | None] = mapped_column(String(40))
    order_type: Mapped[str | None] = mapped_column(String(32))
    time_setup_utc: Mapped[datetime | None] = mapped_column(UTCDateTime)
    time_done_utc: Mapped[datetime | None] = mapped_column(UTCDateTime)
    volume_initial: Mapped[Decimal | None] = mapped_column(Volume)
    price_open: Mapped[Decimal | None] = mapped_column(Price)
    sl_price: Mapped[Decimal | None] = mapped_column(Price)
    tp_price: Mapped[Decimal | None] = mapped_column(Price)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)


class TradePosition(TimestampMixin, Base):
    """Position-level result derived from deals; rebuilt on every sync."""

    __tablename__ = "trade_position"
    __table_args__ = (
        UniqueConstraint("account_id", "external_position_id"),
        Index("ix_trade_position_account_close", "account_id", "close_time"),
        Index("ix_trade_position_account_symbol_close", "account_id", "symbol", "close_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("trading_account.id", ondelete="CASCADE"))
    external_position_id: Mapped[str] = mapped_column(String(80))
    symbol: Mapped[str] = mapped_column(String(40))
    direction: Mapped[Direction] = mapped_column(enum_col(Direction))
    status: Mapped[PositionStatus] = mapped_column(enum_col(PositionStatus))
    volume_lots: Mapped[Decimal] = mapped_column(Volume)
    open_time: Mapped[datetime] = mapped_column(UTCDateTime)
    close_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    open_price: Mapped[Decimal] = mapped_column(Price)
    close_price: Mapped[Decimal | None] = mapped_column(Price)
    realized_gross_profit: Mapped[Decimal] = mapped_column(Money)
    commission: Mapped[Decimal] = mapped_column(Money)
    swap: Mapped[Decimal] = mapped_column(Money)
    fees: Mapped[Decimal] = mapped_column(Money)
    realized_net_profit: Mapped[Decimal] = mapped_column(Money)
    initial_sl_price: Mapped[Decimal | None] = mapped_column(Price)
    initial_tp_price: Mapped[Decimal | None] = mapped_column(Price)
    sl_tp_source: Mapped[SlTpSource] = mapped_column(enum_col(SlTpSource))
    exit_count: Mapped[int] = mapped_column(Integer, default=0)
    trading_session: Mapped[str | None] = mapped_column(String(20))
    account_currency: Mapped[str] = mapped_column(String(3))
    source_metadata: Mapped[dict | None] = mapped_column(JSON)

    annotation: Mapped["TradeAnnotation | None"] = relationship(  # noqa: F821
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
