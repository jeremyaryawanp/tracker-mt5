from datetime import UTC, datetime

from app.integrations.mock.adapter import MockAdapter
from app.services.demo import load_demo_account
from app.services.users import ensure_default_user


def _demo(client, db_session, seed=11):
    user = ensure_default_user(db_session, client.app.state.settings)
    return load_demo_account(db_session, user, seed=seed, adapter=MockAdapter(
        seed=seed, positions=50, end=datetime(2026, 4, 1, tzinfo=UTC)))


def test_summary_matches_reconciled_positions(client, db_session):
    acc = _demo(client, db_session)
    s = client.get("/api/v1/analytics/summary").json()
    usd = s["by_currency"]["USD"]
    assert usd["trade_count"] == 50 and s["timezone"] == "Asia/Jakarta"
    rec = client.get(f"/api/v1/accounts/{acc.id}/reconciliation").json()
    assert round(usd["net_profit"], 2) == float(rec["position_net_total"])
    assert usd["max_drawdown_pct"] is not None  # starting balance from simulated deposit


def test_filters_and_breakdowns(client, db_session):
    _demo(client, db_session)
    all_ = client.get("/api/v1/analytics/summary").json()["by_currency"]["USD"]
    buys = client.get("/api/v1/analytics/summary?direction=BUY").json()["by_currency"]["USD"]
    assert buys["short_count"] == 0 and buys["trade_count"] == all_["long_count"]
    wins = client.get("/api/v1/analytics/summary?outcome=WIN").json()["by_currency"]["USD"]
    assert wins["losses"] == 0
    b = client.get("/api/v1/analytics/breakdown?by=symbol").json()["USD"]
    assert sum(r["trades"] for r in b) == 50
    assert client.get("/api/v1/analytics/breakdown?by=weekday").status_code == 200
    eq = client.get("/api/v1/analytics/equity").json()["USD"]
    assert len(eq) == 50 and eq[0]["balance"] is not None
    empty = client.get("/api/v1/analytics/summary?date_from=2030-01-01").json()
    assert empty["by_currency"] == {}


def test_filter_validation(client):
    assert client.get("/api/v1/analytics/summary?date_from=2026-02-01&date_to=2026-01-01"
                      ).status_code == 422
    assert client.get("/api/v1/analytics/summary?outcome=MAYBE").status_code == 422
    assert client.get("/api/v1/analytics/breakdown?by=nonsense").status_code == 422
