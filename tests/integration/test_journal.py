import csv
import io
from datetime import UTC, datetime

from app.integrations.mock.adapter import MockAdapter
from app.models import TradePosition
from app.services.demo import load_demo_account
from app.services.users import ensure_default_user


def _demo(client, db_session):
    user = ensure_default_user(db_session, client.app.state.settings)
    return load_demo_account(db_session, user, adapter=MockAdapter(
        seed=5, positions=60, end=datetime(2026, 4, 1, tzinfo=UTC)))


def test_demo_annotations_applied_and_listing(client, db_session):
    _demo(client, db_session)
    r = client.get("/api/v1/trades?page_size=10&page=2&sort=net&order=asc").json()
    assert r["total"] == 60 and len(r["items"]) == 10 and r["page"] == 2
    nets = [i["net"] for i in r["items"]]
    assert nets == sorted(nets)
    tags = client.get("/api/v1/tags").json()
    assert tags["mistakes"] or tags["ict_tags"]
    assert client.get("/api/v1/trades?q=XAUUSD").json()["total"] <= 60
    assert client.get("/api/v1/trades?page_size=500").status_code == 422


def test_annotation_roundtrip_and_survives_resync(client, db_session):
    acc = _demo(client, db_session)
    pid = client.get("/api/v1/trades?page_size=1").json()["items"][0]["id"]
    body = {"setup_name": "London Breakout", "rule_followed": False,
            "mistakes": ["FOMO", "FOMO", "Moved SL"], "ict_tags": ["Liquidity Sweep"],
            "personal_notes": "Entered late"}
    r = client.put(f"/api/v1/trades/{pid}/annotation", json=body).json()
    assert r["annotation"]["mistakes"] == ["FOMO", "Moved SL"]
    assert r["annotation"]["rule_followed"] is False
    r = client.put(f"/api/v1/trades/{pid}/annotation", json={"mistakes": []}).json()
    assert r["annotation"]["mistakes"] == [] and r["annotation"]["ict_tags"] == ["Liquidity Sweep"]
    client.post(f"/api/v1/accounts/{acc.id}/rebuild")
    db_session.expire_all()
    assert db_session.get(TradePosition, pid).annotation.setup_name == "London Breakout"
    by_setup = client.get("/api/v1/analytics/summary?setup=London Breakout").json()
    assert by_setup["by_currency"]["USD"]["trade_count"] >= 1
    assert client.put("/api/v1/trades/999999/annotation", json={}).status_code == 404


def test_csv_export_and_formula_injection_guard(client, db_session):
    _demo(client, db_session)
    pid = client.get("/api/v1/trades?page_size=1").json()["items"][0]["id"]
    client.put(f"/api/v1/trades/{pid}/annotation", json={"setup_name": "=HYPERLINK(1)"})
    r = client.get("/api/v1/trades/export.csv")
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 60 and {"net_profit", "r_multiple", "simulated"} <= set(rows[0])
    assert any(x["setup"] == "'=HYPERLINK(1)" for x in rows)
    assert all(not x["net_profit"].startswith("'") for x in rows)


def test_journal_ui_pages(client, db_session):
    _demo(client, db_session)
    r = client.get("/trades?page=2")
    assert r.status_code == 200 and "Page 2 of 3" in r.text and "Export CSV" in r.text
    pid = client.get("/api/v1/trades?page_size=1").json()["items"][0]["id"]
    r = client.get(f"/trades/{pid}")
    assert r.status_code == 200 and "Save journal entry" in r.text
    r = client.post(f"/trades/{pid}", data={"setup_name": "NY Reversal", "rule_followed": "yes",
                                            "mistakes": "Overtrading, Revenge"},
                    follow_redirects=True)
    assert "NY Reversal" in r.text and "Overtrading, Revenge" in r.text
    a = client.get("/analytics")
    assert a.status_code == 200 and "Symbol" in a.text and "Mistake" in a.text
    assert "Trade not found" in client.get("/trades/999999").text
