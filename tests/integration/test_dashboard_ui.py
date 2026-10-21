def test_dashboard_empty_then_demo(client):
    r = client.get("/")
    assert r.status_code == 200 and "No trading accounts yet" in r.text
    r = client.post("/accounts/demo", follow_redirects=False)
    assert r.status_code == 303
    r = client.get("/")
    assert r.status_code == 200
    for text in ("Net profit", "Profit factor", "Equity curve", "SIMULATED", "Plotly.newPlot",
                 "Asia/Jakarta"):
        assert text in r.text


def test_dashboard_filters_and_no_match(client):
    client.post("/accounts/demo")
    r = client.get("/?direction=BUY&date_from=2001-01-01&date_to=2001-01-02")
    assert r.status_code == 200 and "No closed trades match" in r.text
    assert client.get("/?date_from=garbage").status_code == 200
