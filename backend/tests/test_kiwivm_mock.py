"""Mock 客户端电源/快照行为：模块级状态跨实例存活（ClientFactory 每次新建实例）。"""

import pytest

from app.kiwivm.client import KiwiVMError
from app.kiwivm import mock as kvmmock


@pytest.fixture(autouse=True)
def clean_state():
    kvmmock._reset()
    yield
    kvmmock._reset()


async def test_power_stop_then_start_reflected_in_live_info():
    c1 = kvmmock.MockKiwiVMClient("9000001")
    await c1.power("stop")
    c2 = kvmmock.MockKiwiVMClient("9000001")            # 新实例读到同一状态
    live = await c2.get_live_service_info()
    assert live["ve_status"] == "stopped"
    await c2.power("start")
    assert (await c1.get_live_service_info())["ve_status"] == "running"


async def test_power_kill_stops_and_restart_runs():
    c = kvmmock.MockKiwiVMClient("9000001")
    await c.power("kill")
    assert (await c.get_live_service_info())["ve_status"] == "stopped"
    await c.power("restart")
    assert (await c.get_live_service_info())["ve_status"] == "running"


async def test_power_invalid_action_raises():
    c = kvmmock.MockKiwiVMClient("9000001")
    with pytest.raises(KiwiVMError):
        await c.power("explode")


async def test_snapshot_lifecycle():
    c = kvmmock.MockKiwiVMClient("9000001")
    created = await c.snapshot_create("before-upgrade")
    assert created["fileName"]
    lst = await c.snapshot_list()
    assert len(lst["snapshots"]) == 1
    assert lst["snapshots"][0]["description"] == "before-upgrade"
    assert lst["snapshots"][0]["status"] == "complete"
    await c.snapshot_restore(created["fileName"])      # 不抛错即成功
    await c.snapshot_delete(created["fileName"])
    assert (await c.snapshot_list())["snapshots"] == []


async def test_snapshot_missing_file_raises():
    c = kvmmock.MockKiwiVMClient("9000001")
    with pytest.raises(KiwiVMError):
        await c.snapshot_delete("nope")
    with pytest.raises(KiwiVMError):
        await c.snapshot_restore("nope")


async def test_power_state_isolated_per_veid():
    a = kvmmock.MockKiwiVMClient("9000001")
    b = kvmmock.MockKiwiVMClient("9000002")
    await a.power("stop")
    assert (await b.get_live_service_info())["ve_status"] == "running"


async def test_snapshot_persists_across_instances_and_seq_per_veid():
    a1 = kvmmock.MockKiwiVMClient("9000001")
    f1, f2 = await a1.snapshot_create("one"), await a1.snapshot_create("two")
    assert (f1["fileName"], f2["fileName"]) == ("snapshot-001", "snapshot-002")
    a2 = kvmmock.MockKiwiVMClient("9000001")  # 新实例可见（模块级状态的契约）
    assert [s["fileName"] for s in (await a2.snapshot_list())["snapshots"]] == ["snapshot-001", "snapshot-002"]
    assert (await kvmmock.MockKiwiVMClient("9000002").snapshot_create())["fileName"] == "snapshot-001"
