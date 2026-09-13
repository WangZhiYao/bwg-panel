"""KiwiVM 响应 → 我们的库表/DTO 字段映射与单位换算。"""

import json
import re
from datetime import datetime, timezone


def normalize_status(info: dict) -> str:
    if "ve_status" in info:  # KVM
        return info["ve_status"]
    vz = info.get("vz_status")  # OVZ
    if isinstance(vz, dict) and vz.get("status"):
        return vz["status"]
    return "unknown"


def traffic_bytes(info: dict) -> tuple[int, int]:
    """(真实已用, 真实配额)，均乘 monthly_data_multiplier（规格 §5）。"""
    m = float(info.get("monthly_data_multiplier") or 1)
    used = int(float(info.get("data_counter") or 0) * m)
    quota = int(float(info.get("plan_monthly_data") or 0) * m)
    return used, quota


def parse_size_kb(text) -> int | None:
    """'1.0 G' / '256 MB' → KB；解析失败返回 None。"""
    if not isinstance(text, str):
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]?)\s*(?:B)?\s*$", text, re.IGNORECASE)
    if not m:
        return None
    factor = {"": 1, "K": 1, "M": 1024, "G": 1024**2, "T": 1024**3}[m.group(2).upper()]
    return int(float(m.group(1)) * factor)


def plan_bytes_to_kb(value) -> int | None:
    """KiwiVM plan_* 实为裸字节数（JSON number，如 2147483648），纯数字串同此；
    兼容旧假设的 '1.0 G' 带单位写法。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) // 1024
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        return int(value) // 1024
    return parse_size_kb(value)


def sample_from_live(info: dict) -> dict:
    """getLiveServiceInfo → insert_sample 的可选字段 kwargs（字段缺失或格式脏值时为 None）。"""
    used, _ = traffic_bytes(info)
    quota_gb = info.get("ve_disk_quota_gb")
    try:
        disk_quota_b = int(float(quota_gb) * 1024**3) if quota_gb is not None else None
    except (ValueError, TypeError):
        disk_quota_b = None
    try:
        # 真实返回为 /proc/loadavg 风格复合串（"0.32 0.25 0.10 1/335 2886523"），取 1 分钟值
        load_average = float(str(info.get("load_average")).split()[0])
    except (ValueError, IndexError):
        load_average = None
    return {
        "status": normalize_status(info),
        "data_counter": used,
        "disk_used_b": info.get("ve_used_disk_space_b"),
        "disk_quota_b": disk_quota_b,
        "mem_available_kb": info.get("mem_available_kb"),
        "mem_total_kb": plan_bytes_to_kb(info.get("plan_ram")),
        "swap_available_kb": info.get("swap_available_kb"),
        "swap_total_kb": info.get("swap_total_kb"),
        "load_average": load_average,
        "cpu_throttled": 1 if str(info.get("is_cpu_throttled")).lower() in ("1", "true") else 0,
    }


def profile_from_info(info: dict) -> dict:
    """KiwiVM 信息 → servers 表档案列（仅更新出现的非空字段）。"""
    reset = info.get("data_next_reset")
    try:
        reset_iso = (
            datetime.fromtimestamp(int(reset), tz=timezone.utc).isoformat(timespec="seconds")
            if reset else None
        )
    except (ValueError, TypeError, OSError, OverflowError):
        reset_iso = None
    return {
        "node_location": info.get("node_location"),
        "os": info.get("os"),
        "vm_type": info.get("vm_type"),
        "ip_addresses": json.dumps(info["ip_addresses"]) if info.get("ip_addresses") else None,
        "plan_disk": info.get("plan_disk"),
        "plan_ram": info.get("plan_ram"),
        "plan_swap": info.get("plan_swap"),
        "plan_monthly_data": info.get("plan_monthly_data"),
        "monthly_data_multiplier": info.get("monthly_data_multiplier"),
        "data_next_reset": reset_iso,
    }
