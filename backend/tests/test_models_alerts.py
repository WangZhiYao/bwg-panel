from app import models
from app.db import Database


def make_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "a.db"))
    yield db
    db.close()


def make_server(db) -> dict:
    return models.create_server(db, name="A", veid="1", api_key="k")


def test_create_active_resolve_cycle(tmp_path):
    db = next(make_db(tmp_path))
    s = make_server(db)
    aid = models.create_alert(db, server_id=s["id"], type_="offline",
                              message="掉线", triggered_at="2026-09-12T00:00:00+00:00")
    act = models.active_alert(db, s["id"], "offline")
    assert act["id"] == aid
    assert act["notified"] == 0
    assert act["resolved_at"] is None

    models.resolve_alert(db, aid, "2026-09-12T01:00:00+00:00")
    assert models.active_alert(db, s["id"], "offline") is None


def test_create_alert_one_shot(tmp_path):
    db = next(make_db(tmp_path))
    s = make_server(db)
    aid = models.create_alert(db, server_id=s["id"], type_="cpu_throttle",
                              message="节流", triggered_at="2026-09-12T00:00:00+00:00",
                              resolved=True)
    row = db.query_one("SELECT * FROM alerts WHERE id=?", (aid,))
    assert row["resolved_at"] == row["triggered_at"]  # 插入即解决
    assert row["notified"] == 1                       # 且视为已通知


def test_list_alerts_order_and_active_filter(tmp_path):
    db = next(make_db(tmp_path))
    s = make_server(db)
    a1 = models.create_alert(db, server_id=s["id"], type_="offline", message="旧",
                             triggered_at="2026-09-10T00:00:00+00:00")
    models.resolve_alert(db, a1, "2026-09-10T00:30:00+00:00")
    models.create_alert(db, server_id=s["id"], type_="traffic_warn", message="新",
                        triggered_at="2026-09-12T00:00:00+00:00")
    assert [r["message"] for r in models.list_alerts(db, active_only=True)] == ["新"]
    assert [r["message"] for r in models.list_alerts(db)] == ["新", "旧"]  # 触发时间倒序


def test_mark_notified_and_unnotified(tmp_path):
    db = next(make_db(tmp_path))
    s = make_server(db)
    a1 = models.create_alert(db, server_id=s["id"], type_="offline", message="1",
                             triggered_at="2026-09-12T00:00:00+00:00")
    a2 = models.create_alert(db, server_id=s["id"], type_="traffic_warn", message="2",
                             triggered_at="2026-09-12T00:01:00+00:00")
    models.create_alert(db, server_id=s["id"], type_="cpu_throttle", message="3",
                        triggered_at="2026-09-12T00:02:00+00:00", resolved=True)
    assert [r["id"] for r in models.unnotified_alerts(db)] == [a1, a2]  # 一次性已 notified
    models.mark_notified(db, a1)
    assert [r["id"] for r in models.unnotified_alerts(db)] == [a2]


def test_last_throttle_alert_only_counts_throttle(tmp_path):
    db = next(make_db(tmp_path))
    s = make_server(db)
    assert models.last_throttle_alert(db, s["id"]) is None
    models.create_alert(db, server_id=s["id"], type_="offline", message="x",
                        triggered_at="2026-09-12T00:00:00+00:00")
    assert models.last_throttle_alert(db, s["id"]) is None
    models.create_alert(db, server_id=s["id"], type_="cpu_throttle", message="y",
                        triggered_at="2026-09-12T02:00:00+00:00")
    assert models.last_throttle_alert(db, s["id"])["message"] == "y"


def test_ack_flow_and_active_filter_semantics(tmp_path):
    """acknowledged：已读位——active_only 口径为"未解决且未确认"（铃铛/横幅）。"""
    db = next(make_db(tmp_path))
    s = make_server(db)
    a1 = models.create_alert(db, server_id=s["id"], type_="offline", message="1",
                             triggered_at="2026-09-13T00:00:00+00:00")
    a2 = models.create_alert(db, server_id=s["id"], type_="traffic_warn", message="2",
                             triggered_at="2026-09-13T00:01:00+00:00")
    assert [r["id"] for r in models.list_alerts(db, active_only=True)] == [a2, a1]  # 触发时间倒序

    assert models.get_alert(db, a1) is not None
    assert models.get_alert(db, 999) is None
    models.ack_alert(db, a1)   # 确认 a1
    models.ack_alert(db, a1)   # 幂等

    assert [r["id"] for r in models.list_alerts(db, active_only=True)] == [a2]
    rows = {r["id"]: r for r in models.list_alerts(db)}
    assert rows[a1]["acknowledged"] == 1
    assert rows[a2]["acknowledged"] == 0
    # 状态机语义不受影响：a1 仍是 active（同 type 唯一未解决仍指向它）
    assert models.active_alert(db, s["id"], "offline")["id"] == a1
