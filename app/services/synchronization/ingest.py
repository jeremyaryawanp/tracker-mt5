"""Idempotent ingestion of normalized batches into raw broker tables.

Raw deals are keyed by (account_id, external_deal_id): re-sending a deal is counted as a
duplicate, or as an update when broker-side values changed. Positions are rebuilt for every
position touched by the batch (see ``positions.rebuild_positions``).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import SymbolSpec, SyncRun, TradeDeal, TradeOrder, TradingAccount
from app.models.enums import PipSource, SyncStatus
from app.schemas.ingest import IngestBatch, IngestDeal, IngestResult
from app.services.synchronization.positions import rebuild_positions
from app.utils.symbols import base_symbol, classify, derive_pip
from app.utils.timeconv import ServerOffsetUnknown, server_to_utc

log = logging.getLogger(__name__)
MAX_STORED_FAILED_PAYLOAD_DEALS = 5000
CHUNK = 500


class IngestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _apply_account_metadata(account: TradingAccount, batch: IngestBatch) -> None:
    meta = batch.account
    if meta.platform != account.platform:
        raise IngestError(
            "PLATFORM_MISMATCH",
            f"Token belongs to a {account.platform} account but batch is {meta.platform}.",
        )
    if account.login_hash.startswith("pending:"):
        account.login_hash = meta.login_hash
    elif account.login_hash != meta.login_hash:
        raise IngestError(
            "ACCOUNT_MISMATCH",
            "Batch comes from a different broker login than the one linked to this token.",
        )
    account.broker_name = meta.broker_name or account.broker_name
    account.broker_server = meta.broker_server or account.broker_server
    account.account_currency = meta.currency
    account.account_type = meta.account_type
    account.margin_mode = meta.margin_mode
    if meta.initial_balance is not None:
        account.initial_balance = meta.initial_balance


def _upsert_symbols(session: Session, account: TradingAccount, batch: IngestBatch) -> None:
    existing = {s.symbol: s for s in account.symbols}
    seen = {s.symbol: s for s in batch.symbols}
    for name in {d.symbol for d in batch.deals if d.symbol} - seen.keys() - existing.keys():
        seen[name] = None
    for name, spec in seen.items():
        row = existing.get(name)
        if row is None:
            row = SymbolSpec(account_id=account.id, symbol=name)
            session.add(row)
            account.symbols.append(row)
        if spec is not None:
            row.digits = spec.digits
            row.point = spec.point
            row.contract_size = spec.contract_size
            row.tick_size = spec.tick_size
            row.tick_value = spec.tick_value
            row.profit_currency = spec.profit_currency
        row.base_symbol = base_symbol(name)
        row.asset_class = classify(name, spec.path if spec else None)
        if row.pip_size_source != PipSource.USER:
            row.pip_size, row.pip_unit_label = derive_pip(
                name, row.digits, row.point, row.asset_class
            )
            row.pip_size_source = PipSource.DERIVED


def _deal_values(d: IngestDeal, time_utc: datetime) -> dict:
    return {
        "external_order_id": d.external_order_id,
        "external_position_id": d.external_position_id,
        "symbol": d.symbol,
        "deal_type": d.deal_type,
        "entry": d.entry,
        "time_server_raw": d.time.isoformat() if d.time.tzinfo is None else None,
        "time_utc": time_utc,
        "price": d.price,
        "volume": d.volume,
        "profit": d.profit,
        "commission": d.commission,
        "swap": d.swap,
        "fee": d.fee,
        "sl_price": d.sl,
        "tp_price": d.tp,
        "magic": d.magic,
        "comment": d.comment,
        "reason": d.reason,
    }


COMPARED = ("external_position_id", "time_utc", "price", "volume", "profit", "commission",
            "swap", "fee", "sl_price", "tp_price", "entry", "deal_type")


def _changed(row: TradeDeal, values: dict) -> bool:
    return any(getattr(row, k) != values[k] for k in COMPARED)


def _store(session: Session, account: TradingAccount, batch: IngestBatch, run: SyncRun) -> set:
    def to_utc(dt: datetime) -> datetime:
        return server_to_utc(dt, account.server_utc_offset_mode,
                             account.server_utc_offset_minutes, batch.server_utc_offset_minutes)

    touched: set[str] = set()
    ids = list(dict.fromkeys(d.external_deal_id for d in batch.deals))
    existing: dict[str, TradeDeal] = {}
    for i in range(0, len(ids), CHUNK):
        for row in session.scalars(select(TradeDeal).where(
            TradeDeal.account_id == account.id, TradeDeal.external_deal_id.in_(ids[i:i + CHUNK])
        )):
            existing[row.external_deal_id] = row

    for d in batch.deals:
        values = _deal_values(d, to_utc(d.time))
        row = existing.get(d.external_deal_id)
        if row is None:
            row = TradeDeal(account_id=account.id, sync_run_id=run.id,
                            external_deal_id=d.external_deal_id, raw_payload=d.raw, **values)
            session.add(row)
            existing[d.external_deal_id] = row
            run.deals_inserted += 1
        elif _changed(row, values):
            if row.external_position_id:
                touched.add(row.external_position_id)
            for k, v in values.items():
                setattr(row, k, v)
            row.raw_payload = d.raw
            row.sync_run_id = run.id
            run.deals_updated += 1
        else:
            run.deals_duplicate += 1
            continue
        if d.external_position_id:
            touched.add(d.external_position_id)

    orders = {o.external_order_id: o for o in session.scalars(select(TradeOrder).where(
        TradeOrder.account_id == account.id,
        TradeOrder.external_order_id.in_([o.external_order_id for o in batch.orders][:CHUNK * 40]),
    ))} if batch.orders else {}
    for o in batch.orders:
        row = orders.get(o.external_order_id)
        if row is None:
            row = TradeOrder(account_id=account.id, external_order_id=o.external_order_id)
            session.add(row)
            orders[o.external_order_id] = row
        row.sync_run_id = run.id
        row.external_position_id = o.external_position_id
        row.symbol = o.symbol
        row.order_type = o.order_type
        row.time_setup_utc = to_utc(o.time_setup) if o.time_setup else None
        row.time_done_utc = to_utc(o.time_done) if o.time_done else None
        row.volume_initial = o.volume_initial
        row.price_open = o.price_open
        row.sl_price = o.sl
        row.tp_price = o.tp
        row.raw_payload = o.raw
        if o.external_position_id:
            touched.add(o.external_position_id)
    return touched


def ingest_batch(
    session: Session, account: TradingAccount, batch: IngestBatch, *, retry_of_id: int | None = None
) -> SyncRun:
    now = datetime.now(UTC)
    run = SyncRun(account_id=account.id, source=batch.source, started_at=now,
                  deals_received=len(batch.deals), retry_of_id=retry_of_id,
                  range_from=batch.range_from if batch.range_from and batch.range_from.tzinfo
                  else None,
                  range_to=batch.range_to if batch.range_to and batch.range_to.tzinfo else None)
    session.add(run)
    session.flush()
    try:
        _apply_account_metadata(account, batch)
        _upsert_symbols(session, account, batch)
        touched = _store(session, account, batch, run)
        session.flush()
        run.positions_rebuilt = rebuild_positions(session, account, touched)
        run.status = SyncStatus.SUCCESS
        run.finished_at = datetime.now(UTC)
        account.last_synced_at = run.finished_at
        session.commit()
        log.info("sync %s ok: account=%s inserted=%s dup=%s updated=%s positions=%s",
                 run.id, account.id, run.deals_inserted, run.deals_duplicate,
                 run.deals_updated, run.positions_rebuilt)
        return run
    except ServerOffsetUnknown as exc:
        code, message = "SERVER_OFFSET_UNKNOWN", str(exc)
    except IngestError as exc:
        code, message = exc.code, exc.message
    except IntegrityError:
        code, message = "INTEGRITY_ERROR", "Batch conflicts with existing data for this user."
    session.rollback()
    failed = SyncRun(
        account_id=account.id, source=batch.source, status=SyncStatus.FAILED, started_at=now,
        finished_at=datetime.now(UTC), deals_received=len(batch.deals), error_code=code,
        error_message=message[:500], retry_of_id=retry_of_id,
        failed_payload=batch.model_dump(mode="json")
        if len(batch.deals) <= MAX_STORED_FAILED_PAYLOAD_DEALS else None,
    )
    session.add(failed)
    session.commit()
    log.warning("sync %s failed: account=%s code=%s", failed.id, account.id, code)
    return failed


def result_of(run: SyncRun) -> IngestResult:
    return IngestResult(
        sync_run_id=run.id, status=run.status, deals_received=run.deals_received,
        deals_inserted=run.deals_inserted, deals_duplicate=run.deals_duplicate,
        deals_updated=run.deals_updated, positions_rebuilt=run.positions_rebuilt,
        error_code=run.error_code, error_message=run.error_message,
    )
