from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, enum_col
from app.models.enums import (
    AccountType,
    AssetClass,
    MarginMode,
    PipSource,
    Platform,
    ServerOffsetMode,
)
from app.models.types import Money, Price, UTCDateTime


class User(TimestampMixin, Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_timezone: Mapped[str] = mapped_column(String(64), default="Asia/Jakarta")
    week_start: Mapped[str] = mapped_column(String(10), default="MONDAY")

    accounts: Mapped[list["TradingAccount"]] = relationship(back_populates="user")


class TradingAccount(TimestampMixin, Base):
    __tablename__ = "trading_account"
    __table_args__ = (UniqueConstraint("user_id", "platform", "login_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    account_name: Mapped[str] = mapped_column(String(120))
    broker_name: Mapped[str | None] = mapped_column(String(120))
    broker_server: Mapped[str | None] = mapped_column(String(120))
    platform: Mapped[Platform] = mapped_column(enum_col(Platform))
    login_hash: Mapped[str] = mapped_column(String(64))
    account_currency: Mapped[str] = mapped_column(String(3))
    account_type: Mapped[AccountType] = mapped_column(
        enum_col(AccountType), default=AccountType.UNKNOWN
    )
    margin_mode: Mapped[MarginMode] = mapped_column(
        enum_col(MarginMode), default=MarginMode.UNKNOWN
    )
    server_utc_offset_mode: Mapped[ServerOffsetMode] = mapped_column(
        enum_col(ServerOffsetMode), default=ServerOffsetMode.AUTO
    )
    server_utc_offset_minutes: Mapped[int | None] = mapped_column(Integer)
    initial_balance: Mapped[Decimal | None] = mapped_column(Money)
    is_simulated: Mapped[bool] = mapped_column(default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="accounts")
    symbols: Mapped[list["SymbolSpec"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    tokens: Mapped[list["IngestToken"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class IngestToken(TimestampMixin, Base):
    __tablename__ = "ingest_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("trading_account.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(80), default="collector")
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    account: Mapped[TradingAccount] = relationship(back_populates="tokens")


class SymbolSpec(TimestampMixin, Base):
    __tablename__ = "symbol_spec"
    __table_args__ = (UniqueConstraint("account_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("trading_account.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(40))
    base_symbol: Mapped[str | None] = mapped_column(String(40))
    digits: Mapped[int | None] = mapped_column(Integer)
    point: Mapped[Decimal | None] = mapped_column(Price)
    contract_size: Mapped[Decimal | None] = mapped_column(Price)
    tick_size: Mapped[Decimal | None] = mapped_column(Price)
    tick_value: Mapped[Decimal | None] = mapped_column(Price)
    profit_currency: Mapped[str | None] = mapped_column(String(10))
    asset_class: Mapped[AssetClass] = mapped_column(enum_col(AssetClass), default=AssetClass.OTHER)
    pip_size: Mapped[Decimal | None] = mapped_column(Price)
    pip_size_source: Mapped[PipSource] = mapped_column(
        enum_col(PipSource), default=PipSource.DERIVED
    )
    pip_unit_label: Mapped[str | None] = mapped_column(String(80))

    account: Mapped[TradingAccount] = relationship(back_populates="symbols")
