import sqlite3

from app.db import Database, SCHEMA_V1


def test_migrate_creates_all_tables(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    names = {
        r["name"]
        for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"servers", "samples", "alerts", "settings", "ops_log"} <= names
    version = db.query("PRAGMA user_version")[0]["user_version"]
    assert version == 2
    db.close()


def test_migration_v2_adds_acknowledged(tmp_path):
    db = Database(str(tmp_path / "v2.db"))
    cols = {r["name"] for r in db.query("PRAGMA table_info(alerts)")}
    assert "acknowledged" in cols
    assert db.query("PRAGMA user_version")[0]["user_version"] == 2
    # 新告警默认未确认
    db.execute("INSERT INTO servers(name, veid, api_key, created_at) VALUES('A','1','k','2026-09-13T00:00:00+00:00')")
    db.execute("INSERT INTO alerts(server_id, type, message, triggered_at) "
               "VALUES(1,'offline','m','2026-09-13T00:00:00+00:00')")
    assert db.query_one("SELECT acknowledged FROM alerts")["acknowledged"] == 0
    db.close()


def test_migration_upgrades_v1_database(tmp_path):
    """手工造一个 V1 老库（无 acknowledged 列），打开即自动迁移且存量行回填默认值。"""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1 + "\nPRAGMA user_version=1;")
    conn.execute("INSERT INTO servers(name, veid, api_key, created_at) VALUES('A','1','k','2026-09-13T00:00:00+00:00')")
    conn.execute("INSERT INTO alerts(server_id, type, message, triggered_at) "
                 "VALUES(1,'offline','存量','2026-09-13T00:00:00+00:00')")
    conn.commit()
    conn.close()

    db = Database(path)
    assert db.query("PRAGMA user_version")[0]["user_version"] == 2
    assert db.query_one("SELECT acknowledged FROM alerts")["acknowledged"] == 0
    db.close()


def test_reopen_keeps_data_and_version(tmp_path):
    path = str(tmp_path / "t.db")
    db = Database(path)
    db.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?)", ("k", '"v"')
    )
    db.close()

    db2 = Database(path)  # 再次打开不重复迁移
    assert db2.query_one("SELECT value FROM settings WHERE key='k'")["value"] == '"v"'
    assert db2.query("PRAGMA user_version")[0]["user_version"] == 2
    db2.close()


def test_foreign_key_cascade(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    db.execute(
        "INSERT INTO servers(name, veid, api_key, created_at) VALUES('a','1','k','2026-01-01T00:00:00+00:00')"
    )
    sid = db.query_one("SELECT id FROM servers")["id"]
    db.execute(
        "INSERT INTO samples(server_id, ts, status) VALUES(?, '2026-01-01T00:00:00+00:00', 'running')",
        (sid,),
    )
    db.execute("DELETE FROM servers WHERE id=?", (sid,))
    assert db.query_one("SELECT COUNT(*) AS c FROM samples")["c"] == 0
    db.close()


def test_execute_returns_ids(tmp_path):
    with Database(str(tmp_path / "t.db")) as db:
        lastrowid, rowcount = db.execute(
            "INSERT INTO settings(key, value) VALUES('k', 'v')"
        )
        assert (lastrowid, rowcount) == (1, 1)
        _, rowcount = db.execute("DELETE FROM settings WHERE key='nope'")
        assert rowcount == 0


def test_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "a" / "b" / "t.db")
    with Database(path) as db:
        names = {
            r["name"]
            for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"servers", "samples", "alerts", "settings", "ops_log"} <= names
