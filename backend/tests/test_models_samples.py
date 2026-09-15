from datetime import datetime, timedelta, timezone

from app.db import Database
from app import models


def make_db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def iso(**kw):
    return datetime.now(timezone.utc).replace(microsecond=0, **kw).isoformat()


def test_insert_and_latest(tmp_path):
    db = make_db(tmp_path)
    models.create_server(db, name="A", veid="1", api_key="k")
    models.insert_sample(
        db, server_id=1, ts=iso(minute=0), status="running",
        data_counter=1000, disk_used_b=1, disk_quota_b=2,
        mem_available_kb=3, mem_total_kb=4, swap_available_kb=5, swap_total_kb=6,
        load_average=0.5, cpu_throttled=0,
    )
    models.insert_sample(db, server_id=1, ts=iso(minute=5), status="stopped")
    latest = models.latest_sample(db, 1)
    assert latest["ts"] == iso(minute=5)
    assert latest["status"] == "stopped"
    assert latest["data_counter"] is None  # 未提供的字段保持 NULL
    db.close()


def test_samples_since_ascending(tmp_path):
    db = make_db(tmp_path)
    models.create_server(db, name="A", veid="1", api_key="k")
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for i in range(4):
        models.insert_sample(
            db, server_id=1,
            ts=(base + timedelta(hours=i * 6)).isoformat(),
            status="running", data_counter=i * 100,
        )
    since = (base + timedelta(hours=6)).isoformat()
    rows = models.samples_since(db, 1, since)
    assert [r["data_counter"] for r in rows] == [100, 200, 300]
    db.close()


def test_daily_usage_sums_positive_diffs_per_day(tmp_path):
    db = make_db(tmp_path)
    models.create_server(db, name="A", veid="1", api_key="k")
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    points = [
        (base + timedelta(hours=0), 0),
        (base + timedelta(hours=12), 100),
        (base + timedelta(hours=23), 250),
        (base + timedelta(days=1, hours=1), 400),   # 次日：+150（重置日，旧周期尾巴）
        (base + timedelta(days=1, hours=6), 100),   # 计数器回落（月重置）：当日旧周期用量清零
        (base + timedelta(days=1, hours=12), 180),  # +80，从新基线重新起算
    ]
    for ts, counter in points:
        models.insert_sample(
            db, server_id=1, ts=ts.isoformat(),
            status="running", data_counter=counter,
        )
    daily = models.daily_usage(db, 1, base.isoformat())
    assert daily == [
        {"date": "2026-09-01", "bytes": 250},
        {"date": "2026-09-02", "bytes": 80},  # 重置当日只计新周期用量
    ]
    db.close()


def test_daily_usage_reset_day_drops_old_cycle_usage(tmp_path):
    """生产回归（2026-09-15 DC9）：重置点横跨日中时，重置日不得混入旧周期用量。

    北京日 09-15 内：00:00–15:51 旧周期涨到 661GB，15:51 重置归零后涨到 10GB
    → 09-15 桶只应是新周期的 10GB；前一日桶保持完整不受影响。
    """
    db = make_db(tmp_path)
    models.create_server(db, name="A", veid="1", api_key="k")
    # UTC 时刻（Asia/Shanghai = UTC+8）：09-14 16:00 = 北京 09-15 00:00
    points = [
        ("2026-09-14T08:00:00+00:00", 616_000_000_000),  # 北京 09-14 16:00：基线
        ("2026-09-14T15:55:00+00:00", 617_000_000_000),  # 北京 09-14 23:55：+1G → 09-14 桶
        ("2026-09-14T16:05:00+00:00", 618_000_000_000),  # 北京 09-15 00:05：+1G → 09-15 桶（旧周期）
        ("2026-09-15T07:48:00+00:00", 661_000_000_000),  # 北京 09-15 15:48：+43G（旧周期尾巴）
        ("2026-09-15T07:53:00+00:00", 65_000_000),       # 北京 09-15 15:53：重置归零，清掉 09-15 桶
        ("2026-09-15T14:00:00+00:00", 10_000_000_000),   # 北京 09-15 22:00：新周期 +10G
    ]
    for ts, counter in points:
        models.insert_sample(db, server_id=1, ts=ts, status="running", data_counter=counter)
    daily = models.daily_usage(db, 1, "2026-09-14T00:00:00+00:00", "Asia/Shanghai")
    assert [(d["date"], d["bytes"]) for d in daily] == [
        ("2026-09-14", 1_000_000_000),     # 09-14 完整日不受重置影响
        ("2026-09-15", 10_000_000_000 - 65_000_000),  # 只计新周期
    ]
    db.close()


def test_insert_sample_rejects_unknown_columns(tmp_path):
    import pytest
    db = make_db(tmp_path)
    models.create_server(db, name="A", veid="1", api_key="k")
    with pytest.raises(ValueError, match="unknown sample columns"):
        models.insert_sample(
            db, server_id=1, ts=iso(minute=0), status="running",
            disk_used_bytes=123,  # 错误键名
        )
    db.close()


def test_daily_usage_buckets_by_user_timezone(tmp_path):
    db = Database(str(tmp_path / "tz.db"))
    sid = models.create_server(db, name="A", veid="1", api_key="k")["id"]
    # UTC 09-11 23:30 → 09-12 00:30 各一次采样，用量 +30 / +20（23:00 为基线）
    models.insert_sample(db, server_id=sid, ts="2026-09-11T23:00:00+00:00",
                         status="running", data_counter=100)
    models.insert_sample(db, server_id=sid, ts="2026-09-11T23:30:00+00:00",
                         status="running", data_counter=130)
    models.insert_sample(db, server_id=sid, ts="2026-09-12T00:30:00+00:00",
                         status="running", data_counter=150)
    since = "2026-09-01T00:00:00+00:00"

    utc = models.daily_usage(db, sid, since, "UTC")
    assert [(d["date"], d["bytes"]) for d in utc] == [("2026-09-11", 30), ("2026-09-12", 20)]

    cst = models.daily_usage(db, sid, since, "Asia/Shanghai")  # +8：两笔都落 09-12
    assert [(d["date"], d["bytes"]) for d in cst] == [("2026-09-12", 50)]
    db.close()


def test_daily_usage_default_tz_is_utc(tmp_path):
    db = Database(str(tmp_path / "tz2.db"))
    sid = models.create_server(db, name="A", veid="1", api_key="k")["id"]
    models.insert_sample(db, server_id=sid, ts="2026-09-11T23:30:00+00:00",
                         status="running", data_counter=0)
    models.insert_sample(db, server_id=sid, ts="2026-09-11T23:40:00+00:00",
                         status="running", data_counter=10)
    rows = models.daily_usage(db, sid, "2026-09-01T00:00:00+00:00")
    assert rows == [{"date": "2026-09-11", "bytes": 10}]
    db.close()
