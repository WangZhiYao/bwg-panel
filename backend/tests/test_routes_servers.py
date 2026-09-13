from app import models


def login(client):
    client.post("/api/auth/login", json={"password": "pass1234"})


def test_requires_auth(client):
    assert client.get("/api/servers").status_code == 401


def test_crud_flow(client):
    login(client)
    r = client.post(
        "/api/servers",
        json={"name": "VPS-A", "veid": "1234567", "api_key": "private-xyz"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "VPS-A"
    assert "api_key" not in body  # 凭证不回显（规格 §9）

    r = client.get("/api/servers")
    assert [s["name"] for s in r.json()] == ["VPS-A"]

    r = client.patch("/api/servers/1", json={"name": "VPS-A2"})
    assert r.json()["name"] == "VPS-A2"

    assert client.delete("/api/servers/1").status_code == 204
    assert client.get("/api/servers").json() == []


def test_create_validations(client):
    login(client)
    assert client.post("/api/servers", json={"name": "", "veid": "1", "api_key": "k"}).status_code == 400
    assert client.post("/api/servers", json={"name": "A", "veid": "abc", "api_key": "k"}).status_code == 400
    client.post("/api/servers", json={"name": "A", "veid": "1234567", "api_key": "k"})
    r = client.post("/api/servers", json={"name": "B", "veid": "1234567", "api_key": "k"})
    assert r.status_code == 409
    assert r.json()["error"] == "veid_exists"


def test_summary_shape_with_sample(client):
    login(client)
    models.create_server(client.app.state.state.db, name="A", veid="1", api_key="k")
    models.insert_sample(
        client.app.state.state.db, server_id=1,
        ts="2026-09-05T00:00:00+00:00",
        status="running", data_counter=500,
    )
    r = client.get("/api/servers")
    s = r.json()[0]
    assert s["traffic"] == {"used": 500, "quota": 0, "next_reset": None}
    assert s["latest"]["data_counter"] == 500
    assert s["stale"] is True  # 采样时间是很久以前


def test_patch_validations(client):
    login(client)
    client.post("/api/servers", json={"name": "A", "veid": "1111111", "api_key": "k"})
    client.post("/api/servers", json={"name": "B", "veid": "2222222", "api_key": "k"})
    # PATCH 改成别人的 veid → 409
    r = client.patch("/api/servers/1", json={"veid": "2222222"})
    assert r.status_code == 409
    assert r.json()["error"] == "veid_exists"
    # PATCH 改成自己的 veid（不变）→ 200
    assert client.patch("/api/servers/1", json={"veid": "1111111"}).status_code == 200
    # PATCH 空名 → 400
    r = client.patch("/api/servers/1", json={"name": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_name"
    # api_key 空串 → 400（create 与 patch）
    assert client.post("/api/servers", json={"name": "C", "veid": "3333333", "api_key": ""}).status_code == 400
    assert client.patch("/api/servers/1", json={"api_key": ""}).status_code == 400
