from app.kiwivm import mock as kvmmock


def login(client):
    client.post("/api/auth/login", json={"password": "pass1234"})


def setup_function():
    kvmmock._reset()


def test_snapshots_require_auth(client):
    assert client.get("/api/servers/1/snapshots").status_code == 401


def test_snapshot_create_list_delete_flow(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/snapshots", json={"description": "升级前"})
    assert r.status_code == 200
    file_name = r.json()["fileName"]
    assert file_name

    lst = mock_client.get("/api/servers/1/snapshots").json()["snapshots"]
    assert len(lst) == 1
    assert lst[0]["fileName"] == file_name
    assert lst[0]["description"] == "升级前"

    d = mock_client.delete(f"/api/servers/1/snapshots/{file_name}")
    assert d.status_code == 204
    assert mock_client.get("/api/servers/1/snapshots").json()["snapshots"] == []

    ops = mock_client.app.state.state.db.query(
        "SELECT action, result FROM ops_log ORDER BY id")
    assert [(o["action"], o["result"]) for o in ops] == [
        ("snapshot.create", "ok"), ("snapshot.delete", "ok"),
    ]


def test_snapshot_create_without_description(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/snapshots", json={})
    assert r.status_code == 200
    assert r.json()["fileName"]


def test_snapshot_restore_requires_confirm_name(mock_client):
    login(mock_client)
    file_name = mock_client.post("/api/servers/1/snapshots", json={}).json()["fileName"]
    r = mock_client.post(f"/api/servers/1/snapshots/{file_name}/restore", json={})
    assert r.status_code == 400
    assert r.json()["error"] == "confirm_mismatch"
    r2 = mock_client.post(f"/api/servers/1/snapshots/{file_name}/restore",
                         json={"confirm_name": "Mock-A"})
    assert r2.status_code == 200
    assert r2.json()["ok"] is True


def test_snapshot_restore_wrong_confirm_name(mock_client):
    login(mock_client)
    file_name = mock_client.post("/api/servers/1/snapshots", json={}).json()["fileName"]
    r = mock_client.post(f"/api/servers/1/snapshots/{file_name}/restore",
                         json={"confirm_name": "错误"})
    assert r.status_code == 400
    # 被拦截的操作不写审计（只有 create 那一条）
    ops = mock_client.app.state.state.db.query("SELECT action FROM ops_log")
    assert [o["action"] for o in ops] == ["snapshot.create"]


def test_snapshot_delete_missing_502(mock_client):
    login(mock_client)
    r = mock_client.delete("/api/servers/1/snapshots/ghost")
    assert r.status_code == 502
    assert r.json()["error"] == "kiwivm"
    assert r.json()["detail"] == 7                    # 原始错误码透传
    ops = mock_client.app.state.state.db.query("SELECT * FROM ops_log")
    assert len(ops) == 1 and ops[0]["result"] == "error"


def test_snapshots_server_not_found(mock_client):
    login(mock_client)
    assert mock_client.get("/api/servers/99/snapshots").status_code == 404
