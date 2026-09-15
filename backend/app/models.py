"""数据访问层：全部为接受 Database 的模块级函数。"""

import json
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

PROFILE_COLUMNS = (
    "node_location", "os", "vm_type", "ip_addresses",
    "plan_disk", "plan_ram", "plan_swap",
    "plan_monthly_data", "monthly_data_multiplier", "data_next_reset",
)


# ---------- servers ----------

def create_server(db, *, name: str, veid: str, api_key: str) -> dict:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lastrowid, _ = db.execute(
        "INSERT INTO servers(name, veid, api_key, created_at) VALUES(?, ?, ?, ?)",
        (name, veid, api_key, ts),
    )
    return get_server(db, lastrowid)


def list_servers(db) -> list[dict]:
    return db.query("SELECT * FROM servers ORDER BY id")


def get_server(db, server_id: int) -> dict | None:
    return db.query_one("SELECT * FROM servers WHERE id=?", (server_id,))


def get_server_by_veid(db, veid: str) -> dict | None:
    return db.query_one("SELECT * FROM servers WHERE veid=?", (veid,))


def update_server(
    db, server_id: int, *, name: str | None = None,
    veid: str | None = None, api_key: str | None = None,
    profile: dict | None = None,
) -> dict | None:
    sets, params = [], []
    if name is not None:
        sets.append("name=?"); params.append(name)
    if veid is not None:
        sets.append("veid=?"); params.append(veid)
    if api_key is not None:
        sets.append("api_key=?"); params.append(api_key)
    for col in PROFILE_COLUMNS:
        if profile is not None and profile.get(col) is not None:
            sets.append(f"{col}=?"); params.append(profile[col])
    if not sets:
        return get_server(db, server_id)
    params.append(server_id)
    db.execute(f"UPDATE servers SET {', '.join(sets)} WHERE id=?", params)
    return get_server(db, server_id)


def delete_server(db, server_id: int) -> bool:
    _, rowcount = db.execute("DELETE FROM servers WHERE id=?", (server_id,))
    return rowcount > 0


# ---------- settings ----------

def get_setting(db, key: str, default: Any = None) -> Any:
    row = db.query_one("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(row["value"]) if row else default


def set_setting(db, key: str, value: Any) -> None:
    db.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


# ---------- ops_log ----------

def log_op(db, *, server_id: int | None, action: str, result: Literal["ok", "error"],
           detail: dict | None = None) -> int:
    """管理操作审计（规格 §9）：action 如 power.kill / snapshot.create；result: ok|error。"""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lastrowid, _ = db.execute(
        "INSERT INTO ops_log(server_id, action, detail, result, created_at) VALUES(?, ?, ?, ?, ?)",
        (server_id, action,
         json.dumps(detail, ensure_ascii=False) if detail is not None else None,
         result, ts),
    )
    return lastrowid


# ---------- alerts ----------

def create_alert(db, *, server_id: int, type_: str, message: str,
                 triggered_at: str, resolved: bool = False) -> int:
    """插入告警。resolved=True 用于一次性告警（cpu_throttle）：插入即解决且视为已通知。"""
    lastrowid, _ = db.execute(
        "INSERT INTO alerts(server_id, type, message, triggered_at, resolved_at, notified) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (server_id, type_, message, triggered_at,
         triggered_at if resolved else None, 1 if resolved else 0),
    )
    return lastrowid


def active_alert(db, server_id: int, type_: str) -> dict | None:
    """同一 (server, type) 至多一条未解决（规格 §8）。"""
    return db.query_one(
        "SELECT * FROM alerts WHERE server_id=? AND type=? AND resolved_at IS NULL",
        (server_id, type_),
    )


def resolve_alert(db, alert_id: int, resolved_at: str) -> None:
    db.execute("UPDATE alerts SET resolved_at=? WHERE id=?", (resolved_at, alert_id))


def list_alerts(db, active_only: bool = False, limit: int = 200) -> list[dict]:
    """active_only 口径＝"未解决且未确认"（铃铛/横幅的打扰集合）；
    已确认的不再计入，但问题恢复后再次触发会作为新告警重新进入该集合。"""
    where = "WHERE resolved_at IS NULL AND acknowledged=0" if active_only else ""
    return db.query(
        f"SELECT * FROM alerts {where} ORDER BY triggered_at DESC LIMIT ?",
        (limit,),
    )


def get_alert(db, alert_id: int) -> dict | None:
    return db.query_one("SELECT * FROM alerts WHERE id=?", (alert_id,))


def ack_alert(db, alert_id: int) -> None:
    """用户确认（已读）：仅影响铃铛/横幅计数，状态机（触发/恢复）不受影响。幂等。"""
    db.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))


def mark_notified(db, alert_id: int) -> None:
    db.execute("UPDATE alerts SET notified=1 WHERE id=?", (alert_id,))


def unnotified_alerts(db) -> list[dict]:
    """未解决且未推送——SMTP 配好后补发（§8 防轰炸的补齐路径）；旧者优先。"""
    return db.query(
        "SELECT * FROM alerts WHERE resolved_at IS NULL AND notified=0 "
        "ORDER BY triggered_at",
    )


def last_throttle_alert(db, server_id: int) -> dict | None:
    return db.query_one(
        "SELECT * FROM alerts WHERE server_id=? AND type='cpu_throttle' "
        "ORDER BY triggered_at DESC LIMIT 1",
        (server_id,),
    )


# ---------- samples ----------

SAMPLE_COLUMNS = (
    "data_counter", "disk_used_b", "disk_quota_b",
    "mem_available_kb", "mem_total_kb",
    "swap_available_kb", "swap_total_kb",
    "load_average", "cpu_throttled",
)


def insert_sample(db, *, server_id: int, ts: str, status: str, **optional) -> int:
    unknown = set(optional) - set(SAMPLE_COLUMNS)
    if unknown:
        raise ValueError(f"unknown sample columns: {unknown}")
    cols = ["server_id", "ts", "status"]
    params: list = [server_id, ts, status]
    for col in SAMPLE_COLUMNS:
        if optional.get(col) is not None:
            cols.append(col)
            params.append(optional[col])
    placeholders = ", ".join("?" for _ in cols)
    lastrowid, _ = db.execute(
        f"INSERT INTO samples({', '.join(cols)}) VALUES({placeholders})", params
    )
    return lastrowid


def latest_sample(db, server_id: int) -> dict | None:
    return db.query_one(
        "SELECT * FROM samples WHERE server_id=? ORDER BY ts DESC LIMIT 1",
        (server_id,),
    )


def samples_since(db, server_id: int, since_ts: str) -> list[dict]:
    return db.query(
        "SELECT * FROM samples WHERE server_id=? AND ts>=? ORDER BY ts ASC",
        (server_id, since_ts),
    )


def daily_usage(db, server_id: int, since_ts: str, tz_name: str = "UTC") -> list[dict]:
    """相邻采样 data_counter 的正向差值，按指定时区的日历日分桶求和（M4：用户时区）。

    计数器回落＝月度重置：重置当日的旧周期用量无法按日完整归属
    （会造成"新周期已开始、今日用量却仍带旧周期尾巴"），故重置日只计新周期用量。
    """
    tzinfo = ZoneInfo(tz_name)
    per_day: dict[str, int] = {}
    prev: dict | None = None
    for row in samples_since(db, server_id, since_ts):
        if (
            prev is not None
            and row["data_counter"] is not None
            and prev["data_counter"] is not None
        ):
            diff = row["data_counter"] - prev["data_counter"]
            day = datetime.fromisoformat(row["ts"]).astimezone(tzinfo).date().isoformat()
            if diff < 0:
                per_day.pop(day, None)  # 新周期开始：清掉该日已累计的旧周期用量
            elif diff > 0:
                per_day[day] = per_day.get(day, 0) + diff
        prev = row
    return [{"date": d, "bytes": b} for d, b in sorted(per_day.items())]
