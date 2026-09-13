from app.kiwivm import mock as kvmmock


def login(client):
    client.post("/api/auth/login", json={"password": "pass1234"})


def setup_function():
    kvmmock._reset()


def test_power_requires_auth(client):
    r = client.post("/api/servers/1/power", json={"action": "stop"})
    assert r.status_code == 401


def test_power_restart_ok_and_logged(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/power", json={"action": "restart"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert body["latest"]["status"] == "running"        # 操作后立即采样（mock）
    ops = mock_client.app.state.state.db.query("SELECT * FROM ops_log")
    assert len(ops) == 1
    assert ops[0]["action"] == "power.restart"
    assert ops[0]["result"] == "ok"


def test_power_stop_changes_status_via_poll(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/power", json={"action": "stop"})
    assert r.status_code == 200
    assert r.json()["latest"]["status"] == "stopped"    # mock 电源状态即时生效
    r2 = mock_client.post("/api/servers/1/power", json={"action": "start"})
    assert r2.json()["latest"]["status"] == "running"


def test_power_kill_requires_matching_confirm_name(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/power", json={"action": "kill"})  # 缺 confirm_name
    assert r.status_code == 400
    assert r.json()["error"] == "confirm_mismatch"
    r2 = mock_client.post("/api/servers/1/power",
                          json={"action": "kill", "confirm_name": "Mock-A"})
    assert r2.status_code == 200                        # Mock-A 是种子昵称


def test_power_kill_wrong_name_rejected(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/power",
                         json={"action": "kill", "confirm_name": "别的机器"})
    assert r.status_code == 400
    assert r.json()["error"] == "confirm_mismatch"
    ops = mock_client.app.state.state.db.query("SELECT * FROM ops_log")
    assert ops == []                                    # 被拦的操作不写审计


def test_power_invalid_action(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/power", json={"action": "explode"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_action"


def test_power_server_not_found(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/99/power", json={"action": "stop"})
    assert r.status_code == 404


def test_power_kiwivm_failure_502_and_error_logged(mock_client):
    login(mock_client)

    class _Boom:
        async def power(self, action):
            from app.kiwivm.client import KiwiVMError
            raise KiwiVMError(7, "nope")

    class _BoomFactory:
        def for_server(self, server):
            return _Boom()

    mock_client.app.state.state.clients = _BoomFactory()
    r = mock_client.post("/api/servers/1/power", json={"action": "stop"})
    assert r.status_code == 502
    assert r.json()["error"] == "kiwivm"
    assert r.json()["detail"] == 7                      # 原始错误码透传
    ops = mock_client.app.state.state.db.query("SELECT * FROM ops_log")
    assert len(ops) == 1 and ops[0]["result"] == "error"


def test_power_kill_confirm_name_stripped(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/power",
                         json={"action": "kill", "confirm_name": "  Mock-A  "})
    assert r.status_code == 200


def test_power_ok_even_when_followup_sample_fails(mock_client):
    from app.kiwivm.client import KiwiVMError

    class _HalfBoom:
        async def power(self, action):
            return {}

        async def get_live_service_info(self):
            raise KiwiVMError(-1, "采样失败")

    class _HalfBoomFactory:
        def for_server(self, server):
            return _HalfBoom()

    login(mock_client)
    mock_client.app.state.state.clients = _HalfBoomFactory()
    r = mock_client.post("/api/servers/1/power", json={"action": "restart"})
    assert r.status_code == 200                       # 电源操作已成功，采样失败不影响响应
    ops = mock_client.app.state.state.db.query("SELECT result FROM ops_log")
    assert [o["result"] for o in ops] == ["ok"]
