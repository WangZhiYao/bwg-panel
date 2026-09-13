from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import models


def login(client):
    client.post("/api/auth/login", json={"password": "pass1234"})


def test_settings_require_auth(client):
    assert client.get("/api/settings").status_code == 401


def test_get_settings_defaults_without_password(client):
    login(client)
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["threshold_warn"] == 0.8
    assert body["threshold_critical"] == 0.95
    assert body["sample_interval_seconds"] == 300
    assert body["timezone"] == "Asia/Shanghai"
    assert "smtp_pass" not in body  # 永不回传
    assert body["smtp_pass_set"] is False


def test_put_settings_updates_masks_and_trims(client):
    login(client)
    r = client.put("/api/settings", json={
        "smtp_host": "smtp.example.com",
        "smtp_user": "panel@example.com",
        "smtp_pass": "secret",
        "smtp_to": ["a@x.com", " b@x.com "],
    })
    assert r.status_code == 200
    assert r.json()["smtp_to"] == ["a@x.com", "b@x.com"]
    assert "smtp_pass" not in r.json()

    db = client.app.state.state.db
    assert models.get_setting(db, "smtp_pass") == "secret"
    assert client.get("/api/settings").json()["smtp_pass_set"] is True

    # 省略密码 = 保留旧值
    r2 = client.put("/api/settings", json={"smtp_host": "smtp2.example.com"})
    assert models.get_setting(db, "smtp_pass") == "secret"
    # 显式空串 = 清除（切换免认证 SMTP）
    r3 = client.put("/api/settings", json={"smtp_pass": ""})
    assert r3.status_code == 200
    assert models.get_setting(db, "smtp_pass") == ""


def test_put_settings_explicit_null_clears_password(client):
    """显式 null 与空串同义：清除已存密码（三态契约的第三条腿）。"""
    login(client)
    db = client.app.state.state.db
    models.set_setting(db, "smtp_pass", "secret")
    r = client.put("/api/settings", json={"smtp_pass": None})
    assert r.status_code == 200
    assert models.get_setting(db, "smtp_pass") == ""
    assert client.get("/api/settings").json()["smtp_pass_set"] is False


def test_put_settings_validations(client):
    login(client)
    cases = [
        ({"threshold_warn": 0.99}, "invalid_threshold"),
        ({"threshold_critical": 0.5}, "invalid_threshold"),
        ({"threshold_warn": 0}, "invalid_threshold"),
        ({"sample_interval_seconds": 30}, "invalid_interval"),
        ({"sample_interval_seconds": 7200}, "invalid_interval"),
        ({"smtp_port": 0}, "invalid_port"),
        ({"timezone": "Mars/Olympus"}, "invalid_timezone"),
    ]
    for body, code in cases:
        assert client.put("/api/settings", json=body).json()["error"] == code, body


def test_put_settings_valid_timezone_roundtrip(client):
    login(client)
    assert client.put("/api/settings", json={"timezone": "UTC"}).status_code == 200
    assert client.get("/api/settings").json()["timezone"] == "UTC"


def test_put_settings_port_upper_bound_and_edge_cases(client):
    login(client)
    assert client.put("/api/settings", json={"smtp_port": 65536}).json()["error"] == "invalid_port"
    assert client.put("/api/settings", json={"smtp_port": 65535}).status_code == 200
    r = client.put("/api/settings", json={"smtp_to": ["  ", ""]})
    assert r.status_code == 200 and r.json()["smtp_to"] == []
    r2 = client.put("/api/settings", json={"threshold_warn": 0.7, "threshold_critical": 0.9})
    assert r2.status_code == 200
    assert (r2.json()["threshold_warn"], r2.json()["threshold_critical"]) == (0.7, 0.9)


def test_get_settings_includes_disk_mem_thresholds(client):
    login(client)
    body = client.get("/api/settings").json()
    assert body["threshold_disk"] == 0.9
    assert body["threshold_mem"] == 0.9


def test_put_settings_disk_mem_threshold_validation(client):
    """磁盘/内存阈值合法区间 0.5–0.99（50%–99%）。"""
    login(client)
    for bad in (0.4, 1.0):
        assert client.put("/api/settings", json={"threshold_disk": bad}).json()["error"] == "invalid_threshold"
        assert client.put("/api/settings", json={"threshold_mem": bad}).json()["error"] == "invalid_threshold"
    r = client.put("/api/settings", json={"threshold_disk": 0.5, "threshold_mem": 0.95})
    assert r.status_code == 200
    assert (r.json()["threshold_disk"], r.json()["threshold_mem"]) == (0.5, 0.95)


def test_interval_change_reschedules_sampler(client):
    login(client)
    state = client.app.state.state
    stub = MagicMock()
    state.scheduler = stub  # 测试注入；真实调度器由 main 装配

    r = client.put("/api/settings", json={"sample_interval_seconds": 120})
    assert r.status_code == 200
    stub.reschedule_job.assert_called_once_with("sampler", trigger="interval", seconds=120)

    # 调度器未运行（None）时不炸：只落库
    state.scheduler = None
    assert client.put("/api/settings", json={"sample_interval_seconds": 600}).status_code == 200
    assert client.get("/api/settings").json()["sample_interval_seconds"] == 600


def test_test_email_requires_config(client):
    login(client)
    r = client.post("/api/settings/test-email")
    assert r.status_code == 400
    assert r.json()["error"] == "smtp_not_configured"


def test_test_email_ok_and_failure(client, monkeypatch):
    from app import mailer
    login(client)
    db = client.app.state.state.db
    models.set_setting(db, "smtp_host", "s")
    models.set_setting(db, "smtp_user", "u")
    models.set_setting(db, "smtp_to", ["a@x.com"])

    async def ok_send(db, subject, body):
        return True
    monkeypatch.setattr(mailer, "send_mail", ok_send)
    assert client.post("/api/settings/test-email").status_code == 200

    async def bad_send(db, subject, body):
        return False
    monkeypatch.setattr(mailer, "send_mail", bad_send)
    r = client.post("/api/settings/test-email")
    assert r.status_code == 502
    assert r.json()["error"] == "email_send_failed"
