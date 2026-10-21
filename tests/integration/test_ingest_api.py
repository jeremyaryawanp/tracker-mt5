from datetime import UTC, datetime

from app.integrations.mock.adapter import MockAdapter

SECRET_LOGIN = "98765432"


def _create(client, **kw):
    body = {"account_name": "Live", "platform": "MT5", **kw}
    r = client.post("/api/v1/accounts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _batch(login="hash-abcdef12", offset=120, deals=None):
    return {
        "source": "MT5_COLLECTOR",
        "account": {"platform": "MT5", "login_hash": login, "currency": "USD",
                    "broker_name": "Broker", "account_type": "DEMO", "margin_mode": "HEDGING"},
        "server_utc_offset_minutes": offset,
        "deals": deals if deals is not None else [
            {"external_deal_id": "1", "external_position_id": "10", "symbol": "EURUSD",
             "deal_type": "BUY", "entry": "IN", "time": "2026-01-05T10:00:00",
             "price": "1.1000", "volume": "1.00", "commission": "-3.50"},
            {"external_deal_id": "2", "external_position_id": "10", "symbol": "EURUSD",
             "deal_type": "SELL", "entry": "OUT", "time": "2026-01-05T12:00:00",
             "price": "1.1010", "volume": "1.00", "profit": "100.00", "commission": "-3.50"},
        ],
    }


def test_create_account_returns_token_once_and_ingest_is_idempotent(client):
    created = _create(client)
    token = created["ingest_token"]
    assert "ingest_token" not in client.get("/api/v1/accounts").json()[0]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/v1/ingest", json=_batch(), headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["deals_inserted"] == 2

    r = client.post("/api/v1/ingest", json=_batch(), headers=auth)
    assert r.json()["deals_inserted"] == 0 and r.json()["deals_duplicate"] == 2

    changed = _batch()
    changed["deals"][1]["profit"] = "90.00"
    r = client.post("/api/v1/ingest", json=changed, headers=auth)
    assert r.json()["deals_updated"] == 1

    account = client.get("/api/v1/accounts").json()[0]
    assert account["broker_name"] == "Broker" and account["margin_mode"] == "HEDGING"
    runs = client.get(f"/api/v1/accounts/{account['id']}/sync-runs").json()
    assert [run["status"] for run in runs] == ["SUCCESS"] * 3


def test_ingest_converts_server_time_to_utc(client, db_session):
    from sqlalchemy import select

    from app.models import TradeDeal

    token = _create(client)["ingest_token"]
    client.post("/api/v1/ingest", json=_batch(offset=180),
                headers={"Authorization": f"Bearer {token}"})
    deal = db_session.scalar(select(TradeDeal).where(TradeDeal.external_deal_id == "1"))
    assert deal.time_utc == datetime(2026, 1, 5, 7, tzinfo=UTC)
    assert deal.time_server_raw == "2026-01-05T10:00:00"


def test_ingest_rejects_bad_token_and_wrong_account(client):
    assert client.post("/api/v1/ingest", json=_batch()).status_code == 401
    assert client.post("/api/v1/ingest", json=_batch(),
                       headers={"Authorization": "Bearer nope"}).status_code == 401
    token = _create(client)["ingest_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/ingest", json=_batch(), headers=auth).status_code == 200
    r = client.post("/api/v1/ingest", json=_batch(login="other-login-hash"), headers=auth)
    assert r.status_code == 422 and r.json()["error_code"] == "ACCOUNT_MISMATCH"


def test_missing_offset_records_failed_sync_run(client):
    created = _create(client)
    r = client.post("/api/v1/ingest", json=_batch(offset=None),
                    headers={"Authorization": f"Bearer {created['ingest_token']}"})
    assert r.status_code == 422
    assert r.json()["status"] == "FAILED"
    assert r.json()["error_code"] == "SERVER_OFFSET_UNKNOWN"


def test_rotated_token_revokes_previous(client):
    created = _create(client)
    old = created["ingest_token"]
    new = client.post(f"/api/v1/accounts/{created['account']['id']}/token").json()["ingest_token"]
    assert client.post("/api/v1/ingest", json=_batch(),
                       headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.post("/api/v1/ingest", json=_batch(),
                       headers={"Authorization": f"Bearer {new}"}).status_code == 200


def test_validation_errors_are_422(client):
    token = _create(client)["ingest_token"]
    bad = _batch()
    bad["deals"][0]["deal_type"] = "TELEPORT"
    r = client.post("/api/v1/ingest", json=bad, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_body_limit(client, app):
    app.state.settings.ingest_max_bytes = 100
    token = _create(client)["ingest_token"]
    r = client.post("/api/v1/ingest", json=_batch(), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 413


def test_mt4_endpoint(client):
    token = _create(client, platform="MT4", server_utc_offset_mode="FIXED",
                    server_utc_offset_minutes=120)["ingest_token"]
    payload = {
        "account": {"platform": "MT4", "login_hash": "mt4-login-hash", "currency": "USD"},
        "tickets": [{"ticket": "5", "symbol": "EURUSD", "type": 1, "lots": "0.10",
                     "open_time": "2026-01-05T10:00:00", "close_time": "2026-01-05T11:00:00",
                     "open_price": "1.1", "close_price": "1.099", "sl": "0", "tp": "0",
                     "commission": "-0.7", "swap": "0", "profit": "10"}],
    }
    r = client.post("/api/v1/ingest/mt4", json=payload,
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["deals_inserted"] == 2


def test_csv_upload(client):
    created = _create(client, platform="CSV", server_utc_offset_mode="FIXED",
                      server_utc_offset_minutes=0)
    csv_text = ("ticket,symbol,type,volume,open_time,open_price,close_time,close_price,profit\n"
                "1,EURUSD,buy,0.1,2026-01-05 10:00,1.1,2026-01-05 11:00,1.101,10\n")
    r = client.post(f"/api/v1/accounts/{created['account']['id']}/import/csv",
                    files={"file": ("h.csv", csv_text, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["deals_inserted"] == 2


def test_demo_account_is_flagged_simulated(client, db_session):
    from app.services.demo import load_demo_account
    from app.services.users import ensure_default_user

    user = ensure_default_user(db_session, client.app.state.settings)
    adapter = MockAdapter(seed=3, positions=20, end=datetime(2026, 3, 1, tzinfo=UTC))
    account = load_demo_account(db_session, user, seed=3, adapter=adapter)
    assert account.is_simulated
    again = load_demo_account(db_session, user, seed=3, adapter=MockAdapter(
        seed=3, positions=20, end=datetime(2026, 3, 1, tzinfo=UTC)))
    assert again.id == account.id


def test_account_isolation_404(client):
    assert client.get("/api/v1/accounts/999/sync-runs").status_code == 404
    assert SECRET_LOGIN not in client.get("/api/v1/accounts").text
