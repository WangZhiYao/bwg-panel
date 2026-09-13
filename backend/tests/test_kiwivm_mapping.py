from app.kiwivm.mapping import (
    normalize_status, parse_size_kb, profile_from_info,
    sample_from_live, traffic_bytes,
)


def test_normalize_status_kvm_ovz_unknown():
    assert normalize_status({"ve_status": "running"}) == "running"
    assert normalize_status({"vz_status": {"status": "stopped"}}) == "stopped"
    assert normalize_status({}) == "unknown"


def test_traffic_bytes_applies_multiplier():
    used, quota = traffic_bytes(
        {"data_counter": 100, "plan_monthly_data": 1000, "monthly_data_multiplier": 2.5}
    )
    assert used == 250
    assert quota == 2500
    used, quota = traffic_bytes({})  # 缺字段兜底
    assert (used, quota) == (0, 0)


def test_parse_size_kb():
    assert parse_size_kb("1.0 G") == 1048576
    assert parse_size_kb("256 MB") == 262144
    assert parse_size_kb("20 G") == 20971520
    assert parse_size_kb(None) is None
    assert parse_size_kb("garbage") is None


def test_sample_from_live_full_kvm():
    info = {
        "ve_status": "running",
        "data_counter": 500, "monthly_data_multiplier": 2.0,
        "ve_used_disk_space_b": 10**10, "ve_disk_quota_gb": 20,
        "mem_available_kb": 300000, "plan_ram": "1.0 G",
        "swap_available_kb": 100000, "swap_total_kb": 262144,
        "load_average": 0.42, "is_cpu_throttled": True,
    }
    s = sample_from_live(info)
    assert s["status"] == "running"
    assert s["data_counter"] == 1000          # 已乘倍率（规格 §5）
    assert s["disk_quota_b"] == 20 * 1024**3   # GB → 字节
    assert s["mem_total_kb"] == 1048576        # plan_ram 推导
    assert s["cpu_throttled"] == 1


def test_profile_from_info():
    info = {
        "node_location": "DC9 CN2", "os": "Debian 12", "vm_type": "kvm",
        "ip_addresses": ["1.2.3.4", "2607::1"],
        "plan_disk": "20 G", "plan_ram": "1.0 G", "plan_swap": "256 MB",
        "plan_monthly_data": 1024**4, "monthly_data_multiplier": 1.0,
        "data_next_reset": 1759276800,  # 2025-10-01T00:00:00Z
    }
    p = profile_from_info(info)
    assert p["node_location"] == "DC9 CN2"
    assert p["ip_addresses"] == '["1.2.3.4", "2607::1"]'  # JSON 字符串入库
    assert p["data_next_reset"] == "2025-10-01T00:00:00+00:00"
    assert p["plan_monthly_data"] == 1024**4


def test_dirty_inputs_never_raise():
    # ve_disk_quota_gb 为字符串
    s = sample_from_live({"ve_status": "running", "ve_disk_quota_gb": "20"})
    assert s["disk_quota_b"] == 20 * 1024**3
    # 非法配额 → None 而非异常
    assert sample_from_live({"ve_disk_quota_gb": "n/a"})["disk_quota_b"] is None
    # data_next_reset 脏值 → None
    assert profile_from_info({"data_next_reset": "soon"})["data_next_reset"] is None
    # cpu_throttled 字符串 "0" → 0
    assert sample_from_live({"is_cpu_throttled": "0"})["cpu_throttled"] == 0
    # load_average 字符串 → float
    assert sample_from_live({"load_average": "0.42"})["load_average"] == 0.42
    assert sample_from_live({"load_average": "?"})["load_average"] is None


def test_parse_size_kb_edges():
    assert parse_size_kb("1.5TB") == 1024**3 + 512 * 1024**2  # 返回 KB：1.5×1024³
    assert parse_size_kb("512kb") == 512
    assert parse_size_kb("1 G B") == 1048576
    assert parse_size_kb("1.0.5") is None
    assert parse_size_kb("..") is None


# ===== 真实 API 格式回归（2026-09-13 生产抓包，VMID 1761033 / KVM）=====


def test_load_average_real_proc_loadavg_string():
    """真实返回是 /proc/loadavg 风格复合串（1/5/15 分钟 + 进程数 + last pid），取 1 分钟值。"""
    s = sample_from_live({"load_average": "0.32 0.25 0.10 1/335 2886523"})
    assert s["load_average"] == 0.32


def test_load_average_dirty_values_stay_none():
    assert sample_from_live({"load_average": 0.42})["load_average"] == 0.42
    assert sample_from_live({})["load_average"] is None
    assert sample_from_live({"load_average": ""})["load_average"] is None
    assert sample_from_live({"load_average": "?"})["load_average"] is None


def test_mem_total_kb_real_plan_ram_is_raw_bytes():
    """真实 plan_ram 是裸字节数（JSON number 2147483648），非 '1.0 G' 字符串。"""
    assert sample_from_live({"plan_ram": 2147483648})["mem_total_kb"] == 2 * 1024 * 1024
    assert sample_from_live({"plan_ram": 805306368})["mem_total_kb"] == 768 * 1024
    # 纯数字字符串同样按字节（ getServiceInfo 档案里以 TEXT 落库的形态）
    assert sample_from_live({"plan_ram": "2147483648"})["mem_total_kb"] == 2 * 1024 * 1024
    # 旧假设的带单位写法保持兼容
    assert sample_from_live({"plan_ram": "1.0 G"})["mem_total_kb"] == 1024 * 1024
    assert sample_from_live({})["mem_total_kb"] is None
