from fastapi.testclient import TestClient

from app.auth import SESSION_COOKIE


def test_login_success_sets_cookie(client):
    r = client.post("/api/auth/login", json={"password": "pass1234"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert SESSION_COOKIE in r.cookies


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"] == "bad_credentials"


def test_me_requires_session(client):
    assert client.get("/api/auth/me").status_code == 401

    client.post("/api/auth/login", json={"password": "pass1234"})
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"user": "admin"}


def test_logout_clears_session(client):
    client.post("/api/auth/login", json={"password": "pass1234"})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_login_rate_limited(make_app):
    from fastapi.testclient import TestClient

    with TestClient(make_app()) as c:
        for _ in range(5):
            c.post("/api/auth/login", json={"password": "nope"})
        r = c.post("/api/auth/login", json={"password": "pass1234"})
        assert r.status_code == 429
        assert r.json()["error"] == "rate_limited"


def test_successful_logins_not_rate_limited(client):
    for _ in range(6):
        r = client.post("/api/auth/login", json={"password": "pass1234"})
        assert r.status_code == 200  # 成功登录不占限流额度


def test_validation_error_is_flat(client):
    # T9 欠账：422 必须是扁平结构（规格 §10）
    r = client.post("/api/auth/login")  # 缺 body
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "message" in body


def test_login_cookie_secure_when_enabled(make_app):
    app = make_app(cookie_secure=True)
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "pass1234"})
        assert r.status_code == 200
        assert "secure" in r.headers["set-cookie"].lower()


def test_login_cookie_secure_off_by_default(client):
    r = client.post("/api/auth/login", json={"password": "pass1234"})
    assert r.status_code == 200
    assert "secure" not in r.headers["set-cookie"].lower()
