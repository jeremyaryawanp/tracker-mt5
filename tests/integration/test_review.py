import json
from datetime import UTC, datetime

import httpx

from app.integrations.mock.adapter import MockAdapter
from app.services.demo import load_demo_account
from app.services.users import ensure_default_user

END = datetime(2026, 4, 1, tzinfo=UTC)
WEEK = "2026-03-25"  # Wednesday -> week Mon 23 .. Sun 29 March


def _demo(client, db_session):
    user = ensure_default_user(db_session, client.app.state.settings)
    return load_demo_account(db_session, user, adapter=MockAdapter(
        seed=8, positions=120, days=28, end=END))


def test_weekly_review_metrics_comparison_and_discipline(client, db_session):
    _demo(client, db_session)
    r = client.get(f"/api/v1/reviews/weekly?week={WEEK}").json()
    assert r["week_start"] == "2026-03-23" and r["week_end"] == "2026-03-29"
    usd = r["by_currency"]["USD"]
    cur, prev = usd["current"], usd["previous"]
    assert cur["trade_count"] > 0 and prev["trade_count"] > 0
    assert round(usd["delta"]["net_profit"], 6) == round(
        cur["net_profit"] - prev["net_profit"], 6)
    daily = client.get("/api/v1/analytics/summary?date_from=2026-03-23&date_to=2026-03-29"
                       ).json()["by_currency"]["USD"]
    assert daily["trade_count"] == cur["trade_count"]
    d = usd["discipline"]
    assert (d["followed"]["trades"] + d["broken"]["trades"] + d["unknown"]["trades"]
            == cur["trade_count"])
    assert "Net" in r["auto_summary"] and r["reflection"] is None


def test_empty_week_and_reflection_persistence(client, db_session):
    acc = _demo(client, db_session)
    empty = client.get("/api/v1/reviews/weekly?week=2020-01-01").json()
    assert "No closed trades this week" in empty["auto_summary"]
    r = client.put(f"/api/v1/reviews/weekly?week={WEEK}",
                   json={"lessons_learned": "Wait for the retest", "stop_doing": "Revenge"})
    assert r.json()["reflection"]["lessons_learned"] == "Wait for the retest"
    r = client.put("/api/v1/reviews/weekly?week=2026-03-29", json={"stop_doing": "FOMO"})
    refl = r.json()["reflection"]
    assert refl["stop_doing"] == "FOMO" and refl["lessons_learned"] == "Wait for the retest"
    per_acc = client.get(f"/api/v1/reviews/weekly?week={WEEK}&account_id={acc.id}").json()
    assert per_acc["reflection"] is None  # account-scoped review is separate
    assert client.get(f"/api/v1/reviews/weekly?week={WEEK}&account_id=999").status_code == 404


def test_llm_disabled_and_privacy_safe_mocked_call(client, db_session):
    _demo(client, db_session)
    assert client.post(f"/api/v1/reviews/weekly/llm-summary?week={WEEK}").status_code == 409
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["body"] = request.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "Good week."}}]})

    s = client.app.state.settings
    s.llm_reviews_enabled, s.llm_api_key = True, "test-key"
    client.app.state.llm_transport = httpx.MockTransport(handler)
    try:
        r = client.post(f"/api/v1/reviews/weekly/llm-summary?week={WEEK}")
    finally:
        s.llm_reviews_enabled, s.llm_api_key = False, ""
    assert r.status_code == 200 and r.json()["llm_summary"] == "Good week."
    body = json.loads(sent["body"])["messages"][0]["content"]
    for forbidden in ("SIM-", "login", "Simulated annotation", "account_id"):
        assert forbidden not in body
    assert client.get(f"/api/v1/reviews/weekly?week={WEEK}").json()["llm_summary"] == "Good week."


def test_review_ui(client, db_session):
    _demo(client, db_session)
    r = client.get(f"/review?week={WEEK}")
    assert r.status_code == 200 and "This week vs previous" in r.text
    assert "Automatic summary" in r.text and "Disabled." in r.text
    r = client.post(f"/review?week={WEEK}", data={"next_week_goals": "Max 3 trades/day"},
                    follow_redirects=True)
    assert "Max 3 trades/day" in r.text
