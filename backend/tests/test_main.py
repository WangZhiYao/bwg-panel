# 登录路由行为将在 T10 补测（/api/auth/login 属 T10 范围）。

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_no_auth(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_returns_frontend_not_built(make_app, monkeypatch, tmp_path):
    # dist 可能已构建（挂载静态托管），用不存在目录强制走占位分支
    monkeypatch.setattr("app.main._FRONTEND_DIST", tmp_path / "no-such-dist")
    from fastapi.testclient import TestClient
    with TestClient(make_app()) as c:
        r = c.get("/")
        assert r.status_code == 503
        assert r.json()["error"] == "frontend_not_built"


def test_error_shape_is_flat(client):
    r = client.get("/api/no-such-route")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body and "message" in body  # 规格 §10 错误结构


def test_bootstrap_password_seeded(client):
    # client fixture 已触发 lifespan：密码哈希应已写入 settings
    from app import models
    state = client.app.state.state
    assert models.get_setting(state.db, "admin_password_hash")


def test_mock_seeds_demo_alerts(mock_client):
    mock_client.post("/api/auth/login", json={"password": "pass1234"})
    r = mock_client.get("/api/alerts")
    assert r.status_code == 200
    types = {row["type"] for row in r.json()}
    assert {"traffic_warn", "offline", "collect_error"} <= types

    active = mock_client.get("/api/alerts?active=1").json()
    assert len(active) == 1
    assert active[0]["type"] == "traffic_warn"
    assert active[0]["server_name"] == "Mock-A"
