from app import models


def login(client):
    client.post("/api/auth/login", json={"password": "pass1234"})


def test_alerts_require_auth(client):
    assert client.get("/api/alerts").status_code == 401


def test_alerts_list_shape_and_active_filter(client):
    login(client)
    db = client.app.state.state.db
    s = models.create_server(db, name="东京机", veid="1", api_key="k")
    a1 = models.create_alert(db, server_id=s["id"], type_="offline", message="旧",
                             triggered_at="2026-09-10T00:00:00+00:00")
    models.resolve_alert(db, a1, "2026-09-10T00:30:00+00:00")
    models.create_alert(db, server_id=s["id"], type_="traffic_warn", message="新",
                        triggered_at="2026-09-12T00:00:00+00:00")

    rows = client.get("/api/alerts").json()
    assert [x["message"] for x in rows] == ["新", "旧"]
    assert rows[0]["server_name"] == "东京机"
    assert rows[0]["notified"] is False
    assert rows[0]["acknowledged"] is False
    assert rows[0]["resolved_at"] is None
    assert rows[1]["resolved_at"] is not None

    active = client.get("/api/alerts?active=1").json()
    assert [x["message"] for x in active] == ["新"]


def test_ack_endpoint_marks_read_and_exits_active(client):
    login(client)
    db = client.app.state.state.db
    s = models.create_server(db, name="A", veid="1", api_key="k")
    a1 = models.create_alert(db, server_id=s["id"], type_="offline", message="1",
                             triggered_at="2026-09-13T00:00:00+00:00")
    a2 = models.create_alert(db, server_id=s["id"], type_="traffic_warn", message="2",
                             triggered_at="2026-09-13T00:01:00+00:00")
    assert [x["id"] for x in client.get("/api/alerts?active=1").json()] == [a2, a1]

    assert client.post(f"/api/alerts/{a1}/ack").status_code == 200

    active = client.get("/api/alerts?active=1").json()
    assert [x["id"] for x in active] == [a2]
    rows = {x["id"]: x for x in client.get("/api/alerts").json()}
    assert rows[a1]["acknowledged"] is True
    assert rows[a2]["acknowledged"] is False

    # 幂等；不存在 → 404
    assert client.post(f"/api/alerts/{a1}/ack").status_code == 200
    assert client.post("/api/alerts/999/ack").status_code == 404


def test_ack_requires_auth(client):
    assert client.post("/api/alerts/1/ack").status_code == 401
