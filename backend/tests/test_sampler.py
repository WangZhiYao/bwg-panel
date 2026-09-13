import asyncio

from app import models
from app.auth import LoginRateLimiter, SessionManager
from app.db import Database
from app.kiwivm.client import KiwiVMError
from app.scheduler.sampler import sample_all, sample_one
from app.state import AppState, ClientFactory


def make_state(tmp_path) -> AppState:
    db = Database(str(tmp_path / "s.db"))
    return AppState(
        db=db,
        sessions=SessionManager("k"),
        clients=ClientFactory(mock=True),
        mock=True,
        login_limiter=LoginRateLimiter(),
    )


async def test_sample_one_writes_sample_and_profile(tmp_path):
    state = make_state(tmp_path)
    server = models.create_server(state.db, name="A", veid="9000001", api_key="mock")
    ok = await sample_one(state, server)

    assert ok is True
    latest = models.latest_sample(state.db, server["id"])
    assert latest["status"] == "running"
    assert 0 < latest["data_counter"] <= 1024**4
    assert latest["mem_total_kb"] == 1024 * 1024     # plan_ram 1024**3（字节）
    assert latest["cpu_throttled"] == 0

    profile = models.get_server(state.db, server["id"])
    assert profile["node_location"] == "MockLocation"
    assert profile["plan_monthly_data"] == 1024**4
    assert state.consecutive_failures[server["id"]] == 0
    state.db.close()


class _Boom:
    async def get_live_service_info(self):
        raise KiwiVMError(-1, "网络错误或响应无法解析（已重试）")

    async def aclose(self):
        pass


class _BoomFactory:
    def for_server(self, server):
        return _Boom()


async def test_sample_one_failure_counts_and_skips_db(tmp_path):
    state = make_state(tmp_path)
    state.clients = _BoomFactory()
    server = models.create_server(state.db, name="A", veid="1", api_key="k")

    ok1 = await sample_one(state, server)
    ok2 = await sample_one(state, server)

    assert (ok1, ok2) == (False, False)
    assert state.consecutive_failures[server["id"]] == 2
    assert models.latest_sample(state.db, server["id"]) is None  # 失败轮次不落库


async def test_sample_all_iterates_and_refreshes_rate_limit(tmp_path):
    state = make_state(tmp_path)
    models.create_server(state.db, name="A", veid="9000001", api_key="mock")
    models.create_server(state.db, name="B", veid="9000002", api_key="mock")

    await sample_all(state)

    assert len(models.list_servers(state.db)) == 2
    for s in models.list_servers(state.db):
        assert models.latest_sample(state.db, s["id"]) is not None
    assert state.rate_limit_cache is not None            # 每轮顺带刷新点数
    assert state.rate_limit_cache["remaining_points_15min"] == 800
    assert state.last_sample_at is not None


class _MixedFactory:
    """第一台意外崩溃（非 KiwiVMError），第二台正常 —— 验证轮次隔离。"""

    def __init__(self, boom_veid, ok_veid):
        self.boom_veid = boom_veid
        self.ok_veid = ok_veid

    def for_server(self, server):
        if server["veid"] == self.boom_veid:
            class _Crash:
                async def get_live_service_info(self):
                    raise RuntimeError("unexpected")
                async def aclose(self):
                    pass
            return _Crash()
        from app.kiwivm.mock import MockKiwiVMClient
        return MockKiwiVMClient(self.ok_veid)


async def test_sample_all_isolates_unexpected_crash(tmp_path):
    state = make_state(tmp_path)
    models.create_server(state.db, name="A", veid="9000001", api_key="mock")
    models.create_server(state.db, name="B", veid="9000002", api_key="mock")
    state.clients = _MixedFactory("9000001", "9000002")

    await sample_all(state)  # 不得抛 RuntimeError

    # A 崩了没落库；B 正常落库
    a, b = models.list_servers(state.db)
    assert models.latest_sample(state.db, a["id"]) is None
    assert models.latest_sample(state.db, b["id"]) is not None
    assert state.rate_limit_cache is None  # 点数查询走 _Crash（无该方法→异常被吞），缓存保持 None


async def test_failure_then_success_resets_counter(tmp_path):
    state = make_state(tmp_path)
    server = models.create_server(state.db, name="A", veid="9000001", api_key="mock")
    state.clients = _BoomFactory()
    await sample_one(state, server)
    await sample_one(state, server)
    assert state.consecutive_failures[server["id"]] == 2

    state.clients = ClientFactory(mock=True)  # 恢复正常
    ok = await sample_one(state, server)
    assert ok is True
    assert state.consecutive_failures[server["id"]] == 0
    assert models.latest_sample(state.db, server["id"]) is not None


class _HotClient:
    """返回高占比流量（99%）的假客户端，驱动告警路径。"""

    async def get_live_service_info(self):
        return {
            "vm_type": "kvm", "ve_status": "running",
            "node_location": "X", "os": "os", "ip_addresses": [],
            "plan_disk": "20 G", "plan_ram": "1.0 G", "plan_swap": "256 MB",
            "plan_monthly_data": 1000 * 1024**3, "monthly_data_multiplier": 1,
            "data_counter": 990 * 1024**3,
            "ve_used_disk_space_b": 0, "ve_disk_quota_gb": 20,
            "mem_available_kb": 1, "swap_total_kb": 1, "swap_available_kb": 1,
            "load_average": 0.1, "is_cpu_throttled": False,
        }

    async def aclose(self):
        pass


class _HotFactory:
    def for_server(self, server):
        return _HotClient()


async def test_sample_one_success_feeds_alerter(tmp_path):
    state = make_state(tmp_path)
    server = models.create_server(state.db, name="A", veid="1", api_key="k")
    state.clients = _HotFactory()

    ok = await sample_one(state, server)
    await asyncio.sleep(0)  # 让 _trigger 的后台邮件任务（未配置 SMTP → no-op）跑完

    assert ok is True
    assert models.active_alert(state.db, server["id"], "traffic_critical")


async def test_sample_one_failures_raise_collect_error(tmp_path):
    state = make_state(tmp_path)
    server = models.create_server(state.db, name="A", veid="1", api_key="k")
    state.clients = _BoomFactory()

    for _ in range(3):
        await sample_one(state, server)
    await asyncio.sleep(0)

    assert models.active_alert(state.db, server["id"], "collect_error")


async def test_mock_seed_survives_first_round(tmp_path):
    """播种的 active 预警在首轮采样后仍在（Mock-A 保底 85%），历史两条保持已解决。"""
    from app.main import _seed_mock_alerts

    state = make_state(tmp_path)
    a = models.create_server(state.db, name="Mock-A", veid="9000001", api_key="mock")
    b = models.create_server(state.db, name="Mock-B", veid="9000002", api_key="mock")
    _seed_mock_alerts(state.db, a["id"], b["id"])

    await sample_all(state)
    await asyncio.sleep(0)

    assert models.active_alert(state.db, a["id"], "traffic_warn") is not None
    assert models.active_alert(state.db, a["id"], "traffic_critical") is None
    rows = models.list_alerts(state.db)
    assert len([r for r in rows if r["type"] == "offline"]) == 1
    assert len([r for r in rows if r["type"] == "collect_error"]) == 1
