"""Consistency checks between raw deals and derived positions."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SyncRun, TradeDeal, TradePosition, TradingAccount
from app.models.enums import DealType, PositionStatus, SyncStatus
from app.schemas.ingest import IngestBatch
from app.services.synchronization.ingest import ingest_batch

ZERO = Decimal("0")


class RetryNotPossible(ValueError):
    pass


def reconcile(session: Session, account: TradingAccount) -> dict:
    trade = TradeDeal.deal_type.in_([DealType.BUY, DealType.SELL])
    mine = TradeDeal.account_id == account.id
    deal_net = session.scalar(select(func.coalesce(func.sum(
        TradeDeal.profit + TradeDeal.commission + TradeDeal.swap + TradeDeal.fee), 0))
        .where(mine, trade, TradeDeal.external_position_id.is_not(None)))
    orphan = session.scalar(select(func.count()).where(
        mine, trade, TradeDeal.external_position_id.is_(None)))
    cash = session.scalar(select(func.coalesce(func.sum(TradeDeal.profit), 0)).where(
        mine, TradeDeal.deal_type.in_([DealType.BALANCE, DealType.CREDIT])))
    charges = session.scalar(select(func.coalesce(func.sum(
        TradeDeal.profit + TradeDeal.commission + TradeDeal.fee), 0)).where(
        mine, TradeDeal.deal_type.in_([DealType.COMMISSION, DealType.OTHER])))
    pos = TradePosition.account_id == account.id
    position_net = session.scalar(
        select(func.coalesce(func.sum(TradePosition.realized_net_profit), 0)).where(pos))
    open_count = session.scalar(select(func.count()).where(
        pos, TradePosition.status == PositionStatus.OPEN))
    closed_count = session.scalar(select(func.count()).where(
        pos, TradePosition.status == PositionStatus.CLOSED))
    deal_net, position_net = Decimal(str(deal_net)), Decimal(str(position_net))
    difference = (deal_net - position_net).quantize(Decimal("0.01"))
    return {
        "ok": difference == 0 and orphan == 0,
        "deal_net_total": str(deal_net.quantize(Decimal("0.01"))),
        "position_net_total": str(position_net.quantize(Decimal("0.01"))),
        "difference": str(difference),
        "trade_deals_without_position": orphan,
        "open_positions": open_count,
        "closed_positions": closed_count,
        "balance_operations_total": str(Decimal(str(cash)).quantize(Decimal("0.01"))),
        "account_level_charges_total": str(Decimal(str(charges)).quantize(Decimal("0.01"))),
    }


def retry_sync_run(session: Session, account: TradingAccount, run_id: int) -> SyncRun:
    run = session.get(SyncRun, run_id)
    if run is None or run.account_id != account.id:
        raise LookupError("Sync run not found")
    if run.status != SyncStatus.FAILED:
        raise RetryNotPossible("Only failed sync runs can be retried")
    if not run.failed_payload:
        raise RetryNotPossible("Payload was not stored (too large); re-run the collector instead")
    batch = IngestBatch.model_validate(run.failed_payload)
    result = ingest_batch(session, account, batch, retry_of_id=run.id)
    if result.status == SyncStatus.SUCCESS:
        run.failed_payload = None
        session.commit()
    return result
