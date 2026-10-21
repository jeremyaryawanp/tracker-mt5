from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations.mock.adapter import MockAdapter
from app.models import TradeAnnotation, TradePosition
from app.models.enums import (
    DealEntry,
    DealType,
    MarginMode,
    Platform,
    PositionStatus,
    ServerOffsetMode,
    SlTpSource,
    SyncSource,
    SyncStatus,
)
from app.schemas.ingest import IngestAccount, IngestBatch, IngestDeal, IngestOrder
from app.services.accounts import create_account
from app.services.synchronization.ingest import ingest_batch
from app.services.synchronization.positions import rebuild_account
from app.services.synchronization.reconcile import reconcile, retry_sync_run
from app.services.users import ensure_default_user

T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


@pytest.fixture
def account(db_session, settings):
    user = ensure_default_user(db_session, settings)
    acc, _ = create_account(db_session, user, account_name="T", platform=Platform.MT5)
    db_session.commit()
    return acc


def deal(i, pos, kind, entry, minutes, price, vol, profit="0", commission="0", swap="0",
         order=None, sl=None, tp=None):
    return IngestDeal(external_deal_id=str(i), external_position_id=pos,
                      external_order_id=order, symbol="EURUSD", deal_type=kind, entry=entry,
                      time=T0 + timedelta(minutes=minutes), price=Decimal(price),
                      volume=Decimal(vol), profit=Decimal(profit),
                      commission=Decimal(commission), swap=Decimal(swap), sl=sl, tp=tp)


def batch(deals, orders=(), margin=MarginMode.HEDGING, offset=None):
    return IngestBatch(source=SyncSource.MT5_COLLECTOR,
                       account=IngestAccount(platform=Platform.MT5, login_hash="login-hash-1",
                                             currency="USD", margin_mode=margin),
                       server_utc_offset_minutes=offset, deals=list(deals), orders=list(orders))


def positions(db_session, account):
    return {p.external_position_id: p for p in db_session.scalars(
        select(TradePosition).where(TradePosition.account_id == account.id))}


def test_partial_close_is_one_position_with_costs_once(db_session, account):
    run = ingest_batch(db_session, account, batch([
        deal(1, "P1", DealType.BUY, DealEntry.IN, 0, "1.1000", "1.0", commission="-3.50",
             order="P1"),
        deal(2, "P1", DealType.SELL, DealEntry.OUT, 60, "1.1020", "0.5", "100", "-1.75"),
        deal(3, "P1", DealType.SELL, DealEntry.OUT, 120, "1.1040", "0.5", "200", "-1.75", "-0.40"),
    ], orders=[IngestOrder(external_order_id="P1", external_position_id="P1",
                           sl=Decimal("1.0980"), tp=Decimal("1.1050"))]))
    assert run.status == SyncStatus.SUCCESS and run.positions_rebuilt == 1
    p = positions(db_session, account)["P1"]
    assert p.status == PositionStatus.CLOSED and p.exit_count == 2
    assert p.volume_lots == Decimal("1.0")
    assert p.close_price == Decimal("1.1030")
    assert p.realized_gross_profit == Decimal("300")
    assert p.commission == Decimal("-7.00") and p.swap == Decimal("-0.40")
    assert p.realized_net_profit == Decimal("292.60")
    assert p.sl_tp_source == SlTpSource.OPEN_ORDER and p.initial_sl_price == Decimal("1.0980")
    assert p.close_time == T0 + timedelta(minutes=120)
    assert p.trading_session == "LONDON"
    assert reconcile(db_session, account)["ok"]


def test_scale_in_weighted_open_price_and_open_position(db_session, account):
    ingest_batch(db_session, account, batch([
        deal(1, "P2", DealType.SELL, DealEntry.IN, 0, "1.2000", "1.0"),
        deal(2, "P2", DealType.SELL, DealEntry.IN, 30, "1.2030", "2.0"),
        deal(3, "P2", DealType.BUY, DealEntry.OUT, 60, "1.1990", "1.0", "100"),
    ]))
    p = positions(db_session, account)["P2"]
    assert p.direction == "SELL" and p.open_price == Decimal("1.2020")
    assert p.status == PositionStatus.OPEN and p.close_time is None
    assert Decimal(p.source_metadata["open_volume_remaining"]) == Decimal("2")


def test_netting_reversal_splits_segments(db_session, account):
    ingest_batch(db_session, account, batch([
        deal(1, "N1", DealType.BUY, DealEntry.IN, 0, "1.1000", "1.0"),
        deal(2, "N1", DealType.SELL, DealEntry.INOUT, 60, "1.1010", "3.0", "100"),
        deal(3, "N1", DealType.BUY, DealEntry.OUT, 120, "1.1000", "2.0", "200"),
    ], margin=MarginMode.NETTING))
    ps = positions(db_session, account)
    assert set(ps) == {"N1", "N1#2"}
    assert ps["N1"].direction == "BUY" and ps["N1"].realized_net_profit == Decimal("100")
    assert ps["N1#2"].direction == "SELL" and ps["N1#2"].volume_lots == Decimal("2.0")
    assert ps["N1#2"].status == PositionStatus.CLOSED
    assert reconcile(db_session, account)["ok"]


def test_missing_sl_tp_and_last_known_fallback(db_session, account):
    ingest_batch(db_session, account, batch([
        deal(1, "A", DealType.BUY, DealEntry.IN, 0, "1.1", "1"),
        deal(2, "A", DealType.SELL, DealEntry.OUT, 5, "1.1", "1"),
        deal(3, "B", DealType.BUY, DealEntry.IN, 0, "1.1", "1"),
        deal(4, "B", DealType.SELL, DealEntry.OUT, 5, "1.1", "1", sl=Decimal("1.09")),
    ]))
    ps = positions(db_session, account)
    assert ps["A"].sl_tp_source == SlTpSource.NONE and ps["A"].initial_sl_price is None
    assert ps["B"].sl_tp_source == SlTpSource.LAST_KNOWN


def test_resync_updates_position_and_keeps_annotation(db_session, account):
    deals = [deal(1, "P", DealType.BUY, DealEntry.IN, 0, "1.1", "1"),
             deal(2, "P", DealType.SELL, DealEntry.OUT, 5, "1.101", "1", "100")]
    ingest_batch(db_session, account, batch(deals))
    p = positions(db_session, account)["P"]
    db_session.add(TradeAnnotation(trade_position_id=p.id, setup_name="Breakout"))
    db_session.commit()

    again = ingest_batch(db_session, account, batch(deals))
    assert again.deals_duplicate == 2 and again.positions_rebuilt == 0

    deals[1] = deal(2, "P", DealType.SELL, DealEntry.OUT, 5, "1.101", "1", "90")
    changed = ingest_batch(db_session, account, batch(deals))
    assert changed.deals_updated == 1 and changed.positions_rebuilt == 1
    db_session.expire_all()
    p2 = positions(db_session, account)["P"]
    assert p2.id == p.id and p2.realized_net_profit == Decimal("90")
    assert p2.annotation.setup_name == "Breakout"


def test_failed_run_can_be_retried_after_fixing_offset(db_session, account):
    naive = IngestDeal(external_deal_id="9", external_position_id="Z", symbol="EURUSD",
                       deal_type=DealType.BUY, entry=DealEntry.IN, time=datetime(2026, 1, 5, 10),
                       price=Decimal("1.1"), volume=Decimal("1"))
    failed = ingest_batch(db_session, account, batch([naive]))
    assert failed.status == SyncStatus.FAILED and failed.failed_payload
    account.server_utc_offset_mode = ServerOffsetMode.FIXED
    account.server_utc_offset_minutes = 120
    db_session.commit()
    ok = retry_sync_run(db_session, account, failed.id)
    assert ok.status == SyncStatus.SUCCESS and ok.retry_of_id == failed.id
    assert positions(db_session, account)["Z"].open_time == datetime(2026, 1, 5, 8, tzinfo=UTC)
    with pytest.raises(ValueError):
        retry_sync_run(db_session, account, ok.id)


def test_mock_history_reconciles_and_rebuild_is_stable(db_session, settings):
    user = ensure_default_user(db_session, settings)
    acc, _ = create_account(db_session, user, account_name="Sim", platform=Platform.MOCK,
                            login_hash="simulated-00000005", is_simulated=True)
    adapter = MockAdapter(seed=5, positions=60, end=datetime(2026, 5, 1, tzinfo=UTC))
    ingest_batch(db_session, acc, adapter.fetch_batch())
    report = reconcile(db_session, acc)
    assert report["ok"] and report["closed_positions"] == 60 and report["open_positions"] == 0
    before = {k: v.realized_net_profit for k, v in positions(db_session, acc).items()}
    rebuild_account(db_session, acc)
    db_session.commit()
    after = {k: v.realized_net_profit for k, v in positions(db_session, acc).items()}
    assert before == after


def test_api_retry_rebuild_reconciliation(client):
    created = client.post("/api/v1/accounts", json={"account_name": "X"}).json()
    acc_id, token = created["account"]["id"], created["ingest_token"]
    body = batch([deal(1, "P", DealType.BUY, DealEntry.IN, 0, "1.1", "1")]).model_dump(mode="json")
    body["deals"][0]["time"] = "2026-01-05T10:00:00"
    r = client.post("/api/v1/ingest", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422
    run_id = r.json()["sync_run_id"]
    retry = client.post(f"/api/v1/accounts/{acc_id}/sync-runs/{run_id}/retry")
    assert retry.json()["status"] == "FAILED"
    client.patch(f"/api/v1/accounts/{acc_id}",
                 json={"server_utc_offset_mode": "FIXED", "server_utc_offset_minutes": 0})
    r = client.post(f"/api/v1/accounts/{acc_id}/sync-runs/{run_id}/retry")
    assert r.status_code == 200 and r.json()["status"] == "SUCCESS"
    assert client.post(f"/api/v1/accounts/{acc_id}/sync-runs/{run_id}/retry").status_code == 409
    assert client.post(f"/api/v1/accounts/{acc_id}/rebuild").json()["reconciliation"]["ok"]
    assert client.get(f"/api/v1/accounts/{acc_id}/reconciliation").status_code == 200
