"""CSV fallback import.

Supported layout (one row per closed ticket, MT4/MT5 statement style). Header names are
case-insensitive; aliases in COLUMN_ALIASES are accepted:

ticket,symbol,type,volume,open_time,open_price,close_time,close_price,sl,tp,commission,swap,profit,comment

``type`` is buy/sell (or balance). Times are broker server time (naive) unless they carry an
explicit offset (e.g. ``2026-01-05T10:00:00+00:00``).
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.integrations.mt4.normalize import Mt4Ticket, tickets_to_deals
from app.models.enums import Platform, SyncSource
from app.schemas.ingest import IngestAccount, IngestBatch

COLUMN_ALIASES = {
    "ticket": ("ticket", "position", "order", "deal", "position id"),
    "symbol": ("symbol", "item", "instrument"),
    "type": ("type", "direction", "side"),
    "volume": ("volume", "lots", "size"),
    "open_time": ("open_time", "open time", "time"),
    "open_price": ("open_price", "open price", "price"),
    "close_time": ("close_time", "close time"),
    "close_price": ("close_price", "close price"),
    "sl": ("sl", "s/l", "stop loss"),
    "tp": ("tp", "t/p", "take profit"),
    "commission": ("commission",),
    "swap": ("swap",),
    "profit": ("profit",),
    "comment": ("comment",),
}
TYPE_MAP = {"buy": 0, "sell": 1, "balance": 6, "credit": 7, "0": 0, "1": 1}
TIME_FORMATS = ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


class CsvImportError(ValueError):
    pass


def _parse_time(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)  # noqa: DTZ007 - broker server time
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise CsvImportError(f"Unrecognised time value: {value!r}") from exc


def _dec(value: str | None) -> Decimal | None:
    value = (value or "").replace(" ", "").replace(",", "")
    if value == "":
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise CsvImportError(f"Invalid number: {value!r}") from exc


def parse_positions_csv(text: str) -> list[Mt4Ticket]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise CsvImportError("CSV has no header row.")
    lookup = {h.strip().lower(): h for h in reader.fieldnames}
    cols: dict[str, str] = {}
    for key, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                cols[key] = lookup[alias]
                break
    missing = {"ticket", "type", "open_time"} - cols.keys()
    if missing:
        raise CsvImportError(f"Missing required column(s): {', '.join(sorted(missing))}")

    def get(row: dict, key: str) -> str:
        return (row.get(cols[key]) or "").strip() if key in cols else ""

    tickets = []
    for n, row in enumerate(reader, start=2):
        kind = TYPE_MAP.get(get(row, "type").lower())
        if kind is None:
            continue
        try:
            tickets.append(Mt4Ticket(
                ticket=get(row, "ticket"), symbol=get(row, "symbol"), type=kind,
                lots=_dec(get(row, "volume")) or Decimal("0"),
                open_time=_parse_time(get(row, "open_time")),
                close_time=_parse_time(get(row, "close_time")),
                open_price=_dec(get(row, "open_price")), close_price=_dec(get(row, "close_price")),
                sl=_dec(get(row, "sl")), tp=_dec(get(row, "tp")),
                commission=_dec(get(row, "commission")) or Decimal("0"),
                swap=_dec(get(row, "swap")) or Decimal("0"),
                profit=_dec(get(row, "profit")) or Decimal("0"),
                comment=get(row, "comment") or None,
            ))
        except CsvImportError as exc:
            raise CsvImportError(f"Row {n}: {exc}") from exc
    return tickets


def csv_to_batch(text: str, *, login_hash: str, currency: str,
                 server_utc_offset_minutes: int | None = None) -> IngestBatch:
    tickets = parse_positions_csv(text)
    return IngestBatch(
        source=SyncSource.CSV,
        account=IngestAccount(platform=Platform.CSV, login_hash=login_hash, currency=currency),
        server_utc_offset_minutes=server_utc_offset_minutes,
        deals=tickets_to_deals(tickets),
    )
