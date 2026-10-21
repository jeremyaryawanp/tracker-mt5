import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import RateLimiter, hash_password

PW = "correct horse battery"


@pytest.fixture
def auth_client(tmp_path):
    s = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path}/a.db",
                 app_secret_key="test-secret-key-0123456789", log_json=False,
                 admin_password_hash=hash_password(PW, iterations=1000),
                 login_attempts_per_window=3)
    return TestClient(create_app(s))


def test_auth_required_everywhere_when_enabled(auth_client):
    c = auth_client
    for path in ("/", "/calendar", "/trades", "/analytics", "/review", "/accounts"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path
    for path in ("/api/v1/accounts", "/api/v1/analytics/summary", "/api/v1/trades",
                 "/api/v1/reviews/weekly?week=2026-01-01"):
        assert c.get(path).status_code == 401, path
    assert c.get("/api/v1/health").status_code == 200


def test_login_logout_and_session_shared_with_api(auth_client):
    c = auth_client
    r = c.post("/login", data={"username": "admin", "password": "nope"})
    assert "Invalid username or password" in r.text
    r = c.post("/login", data={"username": "admin", "password": PW}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get("/").status_code == 200
    assert c.get("/api/v1/accounts").status_code == 200
    c.get("/logout")
    assert c.get("/api/v1/accounts").status_code == 401


def test_login_rate_limited(auth_client):
    for _ in range(3):
        auth_client.post("/login", data={"username": "admin", "password": "x"})
    r = auth_client.post("/login", data={"username": "admin", "password": PW},
                         follow_redirects=False)
    assert "Too many attempts" in r.text


def test_cross_site_posts_blocked_but_ingest_allowed(client):
    evil = {"Origin": "https://evil.example"}
    assert client.post("/api/v1/accounts/demo", headers=evil).status_code == 403
    assert client.post("/accounts/demo", headers=evil).status_code == 403
    assert client.post("/accounts/demo", headers={"Sec-Fetch-Site": "cross-site"}
                       ).status_code == 403
    same = {"Origin": "http://testserver"}
    assert client.post("/api/v1/accounts/demo", headers=same).status_code == 201
    assert client.post("/api/v1/ingest", headers=evil, json={}).status_code == 401


def test_security_headers(client):
    h = client.get("/").headers
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_ingest_rate_limit(client):
    acc = client.post("/api/v1/accounts", json={"account_name": "A", "platform": "MT5"}).json()
    client.app.state.ingest_limiter = RateLimiter(2, 60)
    hdr = {"Authorization": f"Bearer {acc['ingest_token']}"}
    body = {"source": "MT5_COLLECTOR", "account": {"platform": "MT5", "login_hash": "h" * 64,
                                                   "currency": "USD"},
            "server_utc_offset_minutes": 0}
    codes = [client.post("/api/v1/ingest", headers=hdr, json=body).status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429


def test_rate_limiter_window():
    rl = RateLimiter(2, 10)
    assert rl.hit("k", 0) and rl.hit("k", 1) and not rl.hit("k", 2)
    assert rl.hit("k", 10.5)


def test_accounts_ui_flow(client):
    r = client.post("/accounts", data={"account_name": "My MT5", "platform": "MT5",
                                       "account_currency": "usd",
                                       "server_utc_offset_minutes": "120"},
                    follow_redirects=True)
    assert "Collector token (shown once" in r.text and "My MT5" in r.text
    assert "Collector token (shown once" not in client.get("/accounts").text
    r = client.post("/accounts", data={"account_name": "", "platform": "MT5"},
                    follow_redirects=True)
    assert "Invalid account details" in r.text
    acc_id = client.get("/api/v1/accounts").json()[0]["id"]
    csv_text = ("Ticket,Symbol,Type,Volume,Open Time,Open Price,Close Time,Close Price,"
                "Commission,Swap,Profit\n1,EURUSD,buy,0.10,2026.01.05 10:00:00,1.1000,"
                "2026.01.05 12:00:00,1.1010,-0.70,0,10.00\n")
    r = client.post(f"/accounts/{acc_id}/csv", files={"file": ("h.csv", csv_text, "text/csv")},
                    follow_redirects=True)
    assert "Import SUCCESS: 2 new" in r.text and "Reconciled" in r.text
    r = client.post(f"/accounts/{acc_id}/rebuild", follow_redirects=True)
    assert "Rebuilt 1 positions" in r.text
