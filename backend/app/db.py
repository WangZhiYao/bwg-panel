"""SQLite：线程安全连接 + PRAGMA user_version 版本化迁移。

线程安全（单连接+锁），可安全地经由 asyncio.to_thread 调用。
"""

import sqlite3
import threading
from pathlib import Path

SCHEMA_V1 = """
CREATE TABLE servers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  veid TEXT NOT NULL UNIQUE,
  api_key TEXT NOT NULL,
  node_location TEXT, os TEXT, vm_type TEXT,
  ip_addresses TEXT,
  plan_disk TEXT, plan_ram TEXT, plan_swap TEXT,
  plan_monthly_data INTEGER, monthly_data_multiplier REAL, data_next_reset TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
  ts TEXT NOT NULL,
  status TEXT NOT NULL,
  data_counter INTEGER,
  disk_used_b INTEGER, disk_quota_b INTEGER,
  mem_available_kb INTEGER, mem_total_kb INTEGER,
  swap_available_kb INTEGER, swap_total_kb INTEGER,
  load_average REAL,
  cpu_throttled INTEGER
);
CREATE INDEX idx_samples_server_ts ON samples(server_id, ts);

CREATE TABLE alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  message TEXT NOT NULL,
  triggered_at TEXT NOT NULL,
  resolved_at TEXT,
  notified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE ops_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  server_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT,
  result TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""

# V2（M4 增量，2026-09-13）：告警确认位——用户已读后不再计入铃铛/横幅（状态机不受影响）
SCHEMA_V2 = "ALTER TABLE alerts ADD COLUMN acknowledged INTEGER NOT NULL DEFAULT 0;"


class Database:
    """所有查询走进程内单连接 + 全局锁（本项目写入频率极低，足够）。"""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                self._apply(1, SCHEMA_V1)
                version = 1
            if version < 2:
                self._apply(2, SCHEMA_V2)

    def _apply(self, version: int, script_body: str) -> None:
        script = f"BEGIN;\n{script_body}\nPRAGMA user_version={version};\nCOMMIT;"
        try:
            self._conn.executescript(script)
        except Exception:
            self._conn.rollback()
            raise

    def execute(self, sql: str, params=()) -> tuple[int, int]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            lastrowid, rowcount = cur.lastrowid, cur.rowcount
            self._conn.commit()
        return lastrowid, rowcount

    def query(self, sql: str, params=()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params=()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False
