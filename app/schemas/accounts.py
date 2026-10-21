from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AccountType, MarginMode, Platform, ServerOffsetMode, SyncStatus


class AccountCreate(BaseModel):
    account_name: str = Field(min_length=1, max_length=120)
    platform: Platform = Platform.MT5
    account_currency: str = Field(default="USD", min_length=3, max_length=3)
    server_utc_offset_mode: ServerOffsetMode = ServerOffsetMode.AUTO
    server_utc_offset_minutes: int | None = Field(default=None, ge=-14 * 60, le=14 * 60)

    @model_validator(mode="after")
    def fixed_needs_minutes(self):
        if (self.server_utc_offset_mode == ServerOffsetMode.FIXED
                and self.server_utc_offset_minutes is None):
            raise ValueError("server_utc_offset_minutes is required for FIXED mode")
        return self


class AccountUpdate(BaseModel):
    account_name: str | None = Field(default=None, min_length=1, max_length=120)
    server_utc_offset_mode: ServerOffsetMode | None = None
    server_utc_offset_minutes: int | None = Field(default=None, ge=-14 * 60, le=14 * 60)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_name: str
    platform: Platform
    broker_name: str | None
    broker_server: str | None
    account_currency: str
    account_type: AccountType
    margin_mode: MarginMode
    server_utc_offset_mode: ServerOffsetMode
    server_utc_offset_minutes: int | None
    initial_balance: Decimal | None
    is_simulated: bool
    last_synced_at: datetime | None


class AccountCreated(BaseModel):
    account: AccountOut
    ingest_token: str = Field(description="Shown once. Store it in the collector config.")


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: SyncStatus
    started_at: datetime
    finished_at: datetime | None
    deals_received: int
    deals_inserted: int
    deals_duplicate: int
    deals_updated: int
    positions_rebuilt: int
    error_code: str | None
    error_message: str | None
    retry_of_id: int | None
