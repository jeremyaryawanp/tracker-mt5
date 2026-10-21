from datetime import UTC, datetime

from app.integrations.mock.adapter import MockAdapter
from app.services.demo import load_demo_account
from app.services.users import ensure_default_user


def test_calendar_page_and_day_drilldown(client, db_session):
    user = ensure_default_user(db_session, client.app.state.settings)
    load_demo_account(db_session, user, adapter=MockAdapter(
        seed=3, positions=40, days=30, end=datetime(2026, 3, 31, tzinfo=UTC)))
    r = client.get("/calendar?month=2026-03")
    assert r.status_code == 200 and "March 2026" in r.text and "Month net" in r.text
    assert "hx-get=\"/calendar/day/2026-03-" in r.text
    api = client.get("/api/v1/analytics/calendar?month=2026-03").json()["USD"]
    day = next(c for w in api["weeks"] for c in w["days"] if c["trades"])
    d = client.get(f"/calendar/day/{day['date']}")
    assert d.status_code == 200 and "Details" in d.text
    assert "No closed trades in this month" in client.get("/calendar?month=2001-01").text
    assert client.get("/calendar/day/nope").status_code == 200
    assert client.get("/api/v1/analytics/calendar?month=03-2026").status_code == 422
