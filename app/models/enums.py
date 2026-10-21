from enum import StrEnum


class Platform(StrEnum):
    MT4 = "MT4"
    MT5 = "MT5"
    CSV = "CSV"
    MOCK = "MOCK"


class AccountType(StrEnum):
    REAL = "REAL"
    DEMO = "DEMO"
    CONTEST = "CONTEST"
    UNKNOWN = "UNKNOWN"


class MarginMode(StrEnum):
    HEDGING = "HEDGING"
    NETTING = "NETTING"
    UNKNOWN = "UNKNOWN"


class ServerOffsetMode(StrEnum):
    AUTO = "AUTO"  # offset supplied by the collector per batch
    FIXED = "FIXED"  # server_utc_offset_minutes
    NY_CLOSE = "NY_CLOSE"  # server = New York time + 7h (UTC+2 winter / UTC+3 summer)


class AssetClass(StrEnum):
    FX = "FX"
    METAL = "METAL"
    INDEX = "INDEX"
    CRYPTO = "CRYPTO"
    OTHER = "OTHER"


class PipSource(StrEnum):
    DERIVED = "DERIVED"
    USER = "USER"


class DealType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    BALANCE = "BALANCE"
    CREDIT = "CREDIT"
    COMMISSION = "COMMISSION"
    OTHER = "OTHER"


class DealEntry(StrEnum):
    IN = "IN"
    OUT = "OUT"
    INOUT = "INOUT"
    OUT_BY = "OUT_BY"
    NONE = "NONE"


class Direction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SlTpSource(StrEnum):
    OPEN_ORDER = "OPEN_ORDER"
    OPEN_DEAL = "OPEN_DEAL"
    LAST_KNOWN = "LAST_KNOWN"
    NONE = "NONE"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TagKind(StrEnum):
    MISTAKE = "MISTAKE"
    ICT = "ICT"
    SETUP = "SETUP"
    CUSTOM = "CUSTOM"


class ReviewPeriod(StrEnum):
    WEEK = "WEEK"
    MONTH = "MONTH"
    CUSTOM = "CUSTOM"


class SyncSource(StrEnum):
    MT5_COLLECTOR = "MT5_COLLECTOR"
    MT4_EA = "MT4_EA"
    CSV = "CSV"
    MOCK = "MOCK"


class SyncStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
