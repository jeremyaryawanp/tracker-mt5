"""Normalized ingest batch shared by MT5 collector, MT4 EA, CSV import and mock adapter.

Datetimes: naive values are broker *server* time; timezone-aware values are absolute.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    AccountType,
    DealEntry,
    DealType,
    MarginMode,
    Platform,
    SyncSource,
)


class IngestAccount(BaseModel):
    platform: Platform
    login_hash: str = Field(min_length=8, max_length=64)
    broker_name: str | None = None
    broker_server: str | None = None
    currency: str = Field(min_length=3, max_length=3)
    account_type: AccountType = AccountType.UNKNOWN
    margin_mode: MarginMode = MarginMode.UNKNOWN
    initial_balance: Decimal | None = None

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class IngestSymbol(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    digits: int | None = None
    point: Decimal | None = None
    contract_size: Decimal | None = None
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    profit_currency: str | None = None
    path: str | None = None


class IngestDeal(BaseModel):
    external_deal_id: str = Field(min_length=1, max_length=64)
    external_order_id: str | None = None
    external_position_id: str | None = None
    symbol: str | None = None
    deal_type: DealType
    entry: DealEntry = DealEntry.NONE
    time: datetime
    price: Decimal | None = None
    volume: Decimal | None = None
    profit: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    sl: Decimal | None = None
    tp: Decimal | None = None
    magic: int | None = None
    comment: str | None = Field(default=None, max_length=255)
    reason: str | None = None
    raw: dict | None = None

    @field_validator("sl", "tp")
    @classmethod
    def zero_is_missing(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None or v == 0 else v


class IngestOrder(BaseModel):
    external_order_id: str = Field(min_length=1, max_length=64)
    external_position_id: str | None = None
    symbol: str | None = None
    order_type: str | None = None
    time_setup: datetime | None = None
    time_done: datetime | None = None
    volume_initial: Decimal | None = None
    price_open: Decimal | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None
    raw: dict | None = None

    @field_validator("sl", "tp")
    @classmethod
    def zero_is_missing(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None or v == 0 else v


class IngestBatch(BaseModel):
    schema_version: int = 1
    source: SyncSource
    account: IngestAccount
    range_from: datetime | None = None
    range_to: datetime | None = None
    server_utc_offset_minutes: int | None = Field(default=None, ge=-14 * 60, le=14 * 60)
    symbols: list[IngestSymbol] = Field(default_factory=list)
    deals: list[IngestDeal] = Field(default_factory=list, max_length=200_000)
    orders: list[IngestOrder] = Field(default_factory=list, max_length=200_000)


class IngestResult(BaseModel):
    sync_run_id: int
    status: str
    deals_received: int
    deals_inserted: int
    deals_duplicate: int
    deals_updated: int
    positions_rebuilt: int
    error_code: str | None = None
    error_message: str | None = None
