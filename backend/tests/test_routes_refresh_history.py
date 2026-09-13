import time
from datetime import datetime, timedelta, timezone

from app import models


def login(client):
    client.post("/api/auth/login", json={"password": "pass1234"})


# mock_client fixture：lifespan 已播种 Mock-A(id=1)/Mock-B(id=2)，无需再建服务器


def test_refresh_returns_fresh_summary(mock_client):
    login(mock_client)
    r = mock_client.post("/api/servers/1/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["latest"]["status"] == "running"        # mock 客户端数据
    assert body["traffic"]["used"] > 0
    assert body["traffic"]["quota"] == 1024**4          # 档案已刷新
    assert body["stale"] is False
    assert body["node_location"] == "MockLocation"


def test_refresh_ttl_60s(mock_client):
    login(mock_client)
    assert mock_client.post("/api/servers/1/refresh").status_code == 200
    r = mock_client.post("/api/servers/1/refresh")
    assert r.status_code == 429
    assert r.json()["error"] == "refresh_ttl"


def test_refresh_degrades_when_points_low(mock_client):
    login(mock_client)
    state = mock_client.app.state.state
    state.rate_limit_cache = {"remaining_points_15min": 10}  # 低于水位线
    state.rate_limit_at = time.time()  # 新鲜缓存，降级判定生效
    state.last_refresh = {}  # 清 TTL，验证是点数拦截
    r = mock_client.post("/api/servers/1/refresh")
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limit_low"


def test_refresh_stale_rate_limit_cache_ignored(mock_client):
    # 缓存值低于下限但已陈旧（>900s）→ 视为未知 → 放行
    login(mock_client)
    state = mock_client.app.state.state
    state.rate_limit_cache = {"remaining_points_15min": 10}
    state.rate_limit_at = time.time() - 901
    state.last_refresh = {}
    r = mock_client.post("/api/servers/1/refresh")
    assert r.status_code == 200


class _Boom:
    async def get_live_service_info(self):
        from app.kiwivm.client import KiwiVMError
        raise KiwiVMError(-1, "网络错误或响应无法解析（已重试）")


class _BoomFactory:
    def for_server(self, server):
        return _Boom()


def test_refresh_kiwivm_failure_returns_502(mock_client):
    login(mock_client)
    mock_client.app.state.state.clients = _BoomFactory()
    r = mock_client.post("/api/servers/1/refresh")
    assert r.status_code == 502
    assert r.json()["error"] == "kiwivm"


def test_history_range_and_daily_usage(mock_client):
    login(mock_client)
    db = mock_client.app.state.state.db
    # 相对当前时间造数：取 3 小时前所在 UTC 日的 0 点为基点，样本间距 10 分钟
    # —— 4 个样本落在同一 UTC 日；默认时区 Asia/Shanghai(+8) 下同样同属一日
    #    （UTC 00:00–00:30 → CST 08:00–08:30），单日断言稳定且必然在 7d 窗口内
    base = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    for i, counter in enumerate([0, 100, 250, 400]):
        models.insert_sample(
            db, server_id=1,
            ts=(base + timedelta(minutes=i * 10)).isoformat(),
            status="running", data_counter=counter,
        )
    r = mock_client.get("/api/servers/1/history", params={"range": "7d"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["samples"]) == 4
    assert body["daily_usage"] == [{"date": base.date().isoformat(), "bytes": 400}]


def test_history_daily_usage_respects_timezone_setting(mock_client):
    """锁定路由接线：history 读取 settings.timezone 传入分桶（默认 Asia/Shanghai）。"""
    login(mock_client)
    db = mock_client.app.state.state.db
    # 跨 UTC 午夜的两笔增量：默认 Asia/Shanghai 下同属一日；切到 UTC 才分成两日
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for minutes, counter in ((-20, 0), (-10, 100), (10, 150)):
        models.insert_sample(
            db, server_id=1,
            ts=(today + timedelta(minutes=minutes)).isoformat(),
            status="running", data_counter=counter,
        )
    models.set_setting(db, "timezone", "UTC")
    r = mock_client.get("/api/servers/1/history", params={"range": "7d"})
    assert r.status_code == 200
    buckets = r.json()["daily_usage"]
    assert [(b["date"], b["bytes"]) for b in buckets] == [
        ((today - timedelta(days=1)).date().isoformat(), 100),
        (today.date().isoformat(), 50),
    ]


def test_history_invalid_range(mock_client):
    login(mock_client)
    r = mock_client.get("/api/servers/1/history", params={"range": "1y"})
    assert r.status_code == 400
