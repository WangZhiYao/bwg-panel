import time
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.auth import LoginRateLimiter, SessionManager
from app.db import Database
from app.scheduler import alerter
from app.state import AppState, ClientFactory


def make_state(tmp_path) -> AppState:
    db = Database(str(tmp_path / "al.db"))
    return AppState(
        db=db,
        sessions=SessionManager("k"),
        clients=ClientFactory(mock=True),
        mock=True,
        login_limiter=LoginRateLimiter(),
    )


def make_server(state, **profile) -> dict:
    s = models.create_server(state.db, name="A", veid="1", api_key="k")
    if profile:
        models.update_server(state.db, s["id"], profile=profile)
        s = models.get_server(state.db, s["id"])
    return s


def sample(status="running", used=None, throttled=0, **extra):
    return {"status": status, "data_counter": used, "cpu_throttled": throttled, **extra}


@pytest.fixture(autouse=True)
def _no_mail(monkeypatch):
    """状态机测试隔离邮件路径（test_alerter_mail.py 单独测）。"""
    async def _noop(*a, **k):
        pass
    monkeypatch.setattr(alerter, "_send_and_track", _noop)


# ---------- offline ----------

async def test_offline_debounce_then_recover(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)

    await alerter.check_server(state, server, sample("stopped"), now=1000.0)
    assert models.list_alerts(state.db, active_only=True) == []      # 去抖期内不报

    await alerter.check_server(state, server, sample("stopped"), now=1300.0)
    act = models.active_alert(state.db, server["id"], "offline")     # ≥5 分钟触发
    assert act and "掉线" in act["message"]

    await alerter.check_server(state, server, sample("running"), now=1400.0)
    assert models.active_alert(state.db, server["id"], "offline") is None  # 运行即恢复
    row = models.list_alerts(state.db)[0]
    assert row["resolved_at"] is not None


async def test_offline_retrigger_after_recover(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)
    for t in (1000.0, 1400.0):
        await alerter.check_server(state, server, sample("stopped"), now=t)
    assert models.active_alert(state.db, server["id"], "offline")
    await alerter.check_server(state, server, sample("running"), now=1500.0)
    for t in (2000.0, 2400.0):
        await alerter.check_server(state, server, sample("stopped"), now=t)
    rows = [r for r in models.list_alerts(state.db) if r["type"] == "offline"]
    assert len(rows) == 2  # 恢复后可再触发，两条独立记录


# ---------- traffic ----------

async def test_traffic_warn_critical_and_reset_recover(tmp_path):
    state = make_state(tmp_path)
    quota_b = 100 * 1024**3  # 100 GiB：使 70/85/97/5 GiB 恰为 70%/85%/97%/5% 占比
    server = make_server(state, plan_monthly_data=quota_b, monthly_data_multiplier=1)

    await alerter.check_server(state, server, sample(used=70 * 1024**3), now=1000.0)
    assert models.list_alerts(state.db, active_only=True) == []

    await alerter.check_server(state, server, sample(used=85 * 1024**3), now=1100.0)
    assert models.active_alert(state.db, server["id"], "traffic_warn")
    assert models.active_alert(state.db, server["id"], "traffic_critical") is None

    await alerter.check_server(state, server, sample(used=97 * 1024**3), now=1200.0)
    assert models.active_alert(state.db, server["id"], "traffic_critical")

    # 月度重置：used 骤降 → 两条先后恢复（占比 < 0.8）
    await alerter.check_server(state, server, sample(used=5 * 1024**3), now=1300.0)
    assert models.active_alert(state.db, server["id"], "traffic_warn") is None
    assert models.active_alert(state.db, server["id"], "traffic_critical") is None


async def test_traffic_skips_unfresh_profile_quota_zero(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)  # 无档案 → quota=0 哨兵（交接要点）
    await alerter.check_server(state, server, sample(used=999 * 1024**3), now=1000.0)
    assert models.list_alerts(state.db, active_only=True) == []


async def test_traffic_thresholds_from_settings(tmp_path):
    state = make_state(tmp_path)
    quota_b = 100 * 1024**3  # 60 GiB / 100 GiB = 60% ≥ 自定义阈值 0.5
    models.set_setting(state.db, "threshold_warn", 0.5)
    server = make_server(state, plan_monthly_data=quota_b, monthly_data_multiplier=1)
    await alerter.check_server(state, server, sample(used=60 * 1024**3), now=1000.0)
    assert models.active_alert(state.db, server["id"], "traffic_warn")


# ---------- cpu_throttle ----------

async def test_cpu_throttle_one_shot_and_suppress(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)

    await alerter.check_server(state, server, sample(throttled=1), now=1000.0)
    rows = [r for r in models.list_alerts(state.db) if r["type"] == "cpu_throttle"]
    assert len(rows) == 1
    assert rows[0]["resolved_at"] is not None    # 一次性：插入即解决
    assert rows[0]["notified"] == 1

    await alerter.check_server(state, server, sample(throttled=1), now=1100.0)
    rows = [r for r in models.list_alerts(state.db) if r["type"] == "cpu_throttle"]
    assert len(rows) == 1                        # 2 小时抑制窗口内不重复


async def test_cpu_throttle_retriggers_after_suppress_window(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)
    # 预置 3 小时前的一次性节流告警：抑制窗口（2h）已过 → 可再触发
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")
    models.create_alert(state.db, server_id=server["id"], type_="cpu_throttle",
                        message="旧节流", triggered_at=old_ts, resolved=True)

    await alerter.check_server(state, server, sample(throttled=1), now=time.time())

    rows = [r for r in models.list_alerts(state.db) if r["type"] == "cpu_throttle"]
    assert len(rows) == 2
    new = [r for r in rows if r["triggered_at"] != old_ts][0]
    assert new["resolved_at"] is not None        # 新记录同样一次性
    assert new["notified"] == 1


# ---------- collect_error ----------

async def test_collect_error_trigger_and_recover(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)

    for i in range(3):
        state.consecutive_failures[server["id"]] = i + 1
        await alerter.check_collect(state, server, ok=False)
    assert models.active_alert(state.db, server["id"], "collect_error")

    state.consecutive_failures[server["id"]] = 0
    await alerter.check_collect(state, server, ok=True)
    assert models.active_alert(state.db, server["id"], "collect_error") is None


async def test_collect_error_not_triggered_below_threshold(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)
    state.consecutive_failures[server["id"]] = 2
    await alerter.check_collect(state, server, ok=False)
    assert models.list_alerts(state.db, active_only=True) == []


# ---------- disk_high / mem_high ----------

async def test_disk_high_trigger_and_hysteresis_resolve(tmp_path):
    """≥90% 触发；回落到滞回带内（85%–90%）不恢复；<85% 才恢复（防横跳刷邮件）。"""
    state = make_state(tmp_path)
    server = make_server(state)
    quota = 100 * 1024**3  # 100 GiB：used GiB 数即百分比

    await alerter.check_server(state, server,
                               sample(disk_used_b=91 * 1024**3, disk_quota_b=quota), now=1000.0)
    act = models.active_alert(state.db, server["id"], "disk_high")
    assert act and "磁盘" in act["message"] and "91.0%" in act["message"]

    await alerter.check_server(state, server,
                               sample(disk_used_b=88 * 1024**3, disk_quota_b=quota), now=1100.0)
    assert models.active_alert(state.db, server["id"], "disk_high")  # 滞回带内不恢复

    await alerter.check_server(state, server,
                               sample(disk_used_b=84 * 1024**3, disk_quota_b=quota), now=1200.0)
    assert models.active_alert(state.db, server["id"], "disk_high") is None


async def test_mem_high_trigger_with_custom_threshold(tmp_path):
    state = make_state(tmp_path)
    models.set_setting(state.db, "threshold_mem", 0.8)
    server = make_server(state)
    total_kb = 1024 * 1024  # 1 GiB

    await alerter.check_server(state, server,
                               sample(mem_available_kb=int(total_kb * 0.15), mem_total_kb=total_kb),
                               now=1000.0)
    act = models.active_alert(state.db, server["id"], "mem_high")
    assert act and "内存" in act["message"] and "85.0%" in act["message"]


async def test_disk_mem_missing_data_skipped(tmp_path):
    """缺 disk_quota_b / mem_total_kb（档案未刷新或旧样本）→ 跳过不触发。"""
    state = make_state(tmp_path)
    server = make_server(state)
    await alerter.check_server(state, server,
                               sample(disk_used_b=999, mem_available_kb=1), now=1000.0)
    assert models.list_alerts(state.db, active_only=True) == []


async def test_disk_high_no_duplicate_while_active(tmp_path):
    state = make_state(tmp_path)
    server = make_server(state)
    quota = 100 * 1024**3
    s = sample(disk_used_b=95 * 1024**3, disk_quota_b=quota)
    await alerter.check_server(state, server, s, now=1000.0)
    await alerter.check_server(state, server, s, now=1100.0)
    rows = [r for r in models.list_alerts(state.db) if r["type"] == "disk_high"]
    assert len(rows) == 1  # 活动期内重复超标不重复告警
