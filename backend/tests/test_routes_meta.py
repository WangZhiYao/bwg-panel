def test_meta_requires_auth(client):
    assert client.get("/api/meta").status_code == 401


def test_meta_shape(mock_client):
    mock_client.post("/api/auth/login", json={"password": "pass1234"})
    state = mock_client.app.state.state
    state.rate_limit_cache = {"remaining_points_15min": 800, "remaining_points_24h": 9000}
    state.last_sample_at = 1757000000.0
    r = mock_client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] is True
    assert body["last_sample_at"] == 1757000000.0
    assert body["rate_limit"]["remaining_points_15min"] == 800
    from app.version import VERSION

    assert body["version"] == VERSION
