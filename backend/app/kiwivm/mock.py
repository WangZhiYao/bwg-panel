"""离线假客户端：返回与 KVM getLiveServiceInfo 同构的数据，供 --mock 演示与测试。
电源/快照状态存模块级字典（ClientFactory 每次新建实例，实例状态会丢）。"""

import time

from app.kiwivm.client import KiwiVMError

_POWER: dict[str, str] = {}          # veid → ve_status
_SNAPSHOTS: dict[str, list[dict]] = {}  # veid → 快照列表
_SNAP_SEQ: dict[str, int] = {}       # veid → 自增序号（文件名用）

VALID_ACTIONS = ("start", "stop", "restart", "kill")


def _reset() -> None:
    """测试隔离用：清空模块级状态。"""
    _POWER.clear()
    _SNAPSHOTS.clear()
    _SNAP_SEQ.clear()


class MockKiwiVMClient:
    def __init__(self, veid: str):
        self.veid = veid
        self._seed = (sum(ord(c) for c in veid) % 900) / 1000.0  # 0.0–0.9，确定性

    async def aclose(self) -> None:
        pass

    async def get_live_service_info(self) -> dict:
        now = time.time()
        month_sec = 30 * 86400
        progress = (now % month_sec) / month_sec
        quota = 1024**4  # 1 TB
        used = min(int(quota * (0.05 + 0.8 * progress) * (0.5 + self._seed)), quota)
        if self.veid == "9000001":  # Mock-A 演示机：保底 ≥85%——真实演化永不越 72%，会让播种的预警告警首轮即"恢复"
            used = max(used, int(quota * 0.85))
        tail = int("".join(ch for ch in self.veid if ch.isdigit())[-2:] or 10)
        return {
            "vm_type": "kvm",
            "ve_status": _POWER.get(self.veid, "running"),
            "node_location": "MockLocation",
            "node_alias": "MOCK",
            "os": "mock-os-12",
            "hostname": f"mock-{self.veid}",
            "ip_addresses": [f"192.0.2.{10 + tail % 200}"],
            "plan_disk": 20 * 1024**3, "plan_ram": 1024**3, "plan_swap": 256 * 1024**2,
            "plan_monthly_data": quota,
            "monthly_data_multiplier": 1,
            "data_counter": used,
            "data_next_reset": int(now + (month_sec - now % month_sec)),
            "ve_used_disk_space_b": int(20 * 1024**3 * (0.1 + 0.5 * self._seed)),
            "ve_disk_quota_gb": "20",
            "mem_available_kb": int(600 * 1024 * (0.3 + self._seed)),
            "swap_total_kb": 262144, "swap_available_kb": 250000,
            # 真实 API 返回 /proc/loadavg 风格复合串；未节流时 is_cpu_throttled 为空串
            "load_average": f"{0.1 + self._seed:.2f} {0.1 + self._seed:.2f} {0.05 + self._seed:.2f} 1/100 4242",
            "is_cpu_throttled": "",
            "ssh_port": 22,
        }

    async def get_service_info(self) -> dict:
        return await self.get_live_service_info()

    async def get_rate_limit_status(self) -> dict:
        return {"remaining_points_15min": 800, "remaining_points_24h": 9000}

    # ---------- 电源与快照（与 KiwiVMClient 同构） ----------

    async def power(self, action: str) -> dict:
        if action not in VALID_ACTIONS:
            raise KiwiVMError(-1, f"invalid action: {action}")
        _POWER[self.veid] = "running" if action in ("start", "restart") else "stopped"
        return {}

    async def snapshot_list(self) -> dict:
        return {"snapshots": [dict(s) for s in _SNAPSHOTS.get(self.veid, [])]}

    async def snapshot_create(self, description: str = "") -> dict:
        seq = _SNAP_SEQ.get(self.veid, 0) + 1
        _SNAP_SEQ[self.veid] = seq
        snap = {
            "fileName": f"snapshot-{seq:03d}",
            "timestamp": int(time.time()),
            "status": "complete",
            "description": description or "",
            "size": 1024**3,  # 1 GB 假大小
        }
        _SNAPSHOTS.setdefault(self.veid, []).append(snap)
        return {"fileName": snap["fileName"]}

    async def snapshot_delete(self, file_name: str) -> dict:
        lst = _SNAPSHOTS.get(self.veid, [])
        for i, s in enumerate(lst):
            if s["fileName"] == file_name:
                del lst[i]
                return {}
        raise KiwiVMError(7, "snapshot not found")

    async def snapshot_restore(self, file_name: str) -> dict:
        if not any(s["fileName"] == file_name for s in _SNAPSHOTS.get(self.veid, [])):
            raise KiwiVMError(7, "snapshot not found")
        return {}
