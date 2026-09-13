from datetime import datetime, timedelta, timezone

from app import models
from app.auth import LoginRateLimiter, SessionManager
from app.db import Database
from app.scheduler import alerter
from app.state import AppState, ClientFactory


def make_state(tmp_path) -> AppState:
    db = Database(str(tmp_path / "am.db"))
    return AppState(
        db=db,
        sessions=SessionManager("k"),
        clients=ClientFactory(mock=True),
        mock=True,
        login_limiter=LoginRateLimiter(),
    )


def make_server(state) -> dict:
    return models.create_server(state.db, name="A", veid="1", api_key="k")


def patch_send(monkeypatch, result):
    """把 mailer.send_mail 换成记录调用的假实现（alerter 经模块属性引用，补丁生效）。"""
    sent = []

    async def fake(db, subject, body):
        sent.append((subject, body))
        return result

    monkeypatch.setattr(alerter.mailer, "send_mail", fake)
    return sent


async def test_send_and_track_success_marks_notified_and_clears_email_error(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    server = make_server(state)
    aid = models.create_alert(state.db, server_id=server["id"], type_="offline",
                              message="m", triggered_at="2026-09-12T00:00:00+00:00")
    eid = models.create_alert(state.db, server_id=server["id"], type_="email_error",
                              message="旧故障", triggered_at="2026-09-12T00:00:00+00:00")
    sent = patch_send(monkeypatch, True)

    await alerter._send_and_track(state, server, subject="s", body="b", alert_id=aid)

    assert sent == [("s", "b")]
    assert state.db.query_one("SELECT notified FROM alerts WHERE id=?", (aid,))["notified"] == 1
    assert state.db.query_one("SELECT resolved_at FROM alerts WHERE id=?", (eid,))["resolved_at"]


async def test_send_and_track_failure_raises_email_error(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    server = make_server(state)
    aid = models.create_alert(state.db, server_id=server["id"], type_="offline",
                              message="m", triggered_at="2026-09-12T00:00:00+00:00")
    patch_send(monkeypatch, False)

    await alerter._send_and_track(state, server, subject="主题X", body="b", alert_id=aid)

    assert state.db.query_one("SELECT notified FROM alerts WHERE id=?", (aid,))["notified"] == 0
    act = models.active_alert(state.db, server["id"], "email_error")
    assert act and "主题X" in act["message"]
    # 再失败一次不重复记（每机至多一条 active email_error）
    await alerter._send_and_track(state, server, subject="主题X", body="b", alert_id=aid)
    assert len([a for a in models.list_alerts(state.db, active_only=True)
                if a["type"] == "email_error"]) == 1


async def test_send_and_track_unconfigured_is_noop(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    server = make_server(state)
    aid = models.create_alert(state.db, server_id=server["id"], type_="offline",
                              message="m", triggered_at="2026-09-12T00:00:00+00:00")
    patch_send(monkeypatch, None)

    await alerter._send_and_track(state, server, subject="s", body="b", alert_id=aid)

    assert state.db.query_one("SELECT notified FROM alerts WHERE id=?", (aid,))["notified"] == 0
    # 只剩这条 offline 处于未解决，且绝不产生 email_error
    assert [a["type"] for a in models.list_alerts(state.db, active_only=True)] == ["offline"]


async def test_retry_unnotified_sends_pending_only(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    server = make_server(state)
    monkeypatch.setattr(alerter.mailer, "smtp_configured", lambda db: True)
    sent = patch_send(monkeypatch, True)
    a1 = models.create_alert(state.db, server_id=server["id"], type_="offline",
                             message="待补发", triggered_at="2026-09-12T00:00:00+00:00")
    models.create_alert(state.db, server_id=server["id"], type_="cpu_throttle",
                        message="一次性", triggered_at="2026-09-12T00:01:00+00:00",
                        resolved=True)  # 一次性已 resolved，不在补发集合

    await alerter.retry_unnotified(state)

    assert len(sent) == 1 and "待补发" in sent[0][1]
    assert state.db.query_one("SELECT notified FROM alerts WHERE id=?", (a1,))["notified"] == 1


async def test_retry_unnotified_skips_when_unconfigured(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    make_server(state)
    monkeypatch.setattr(alerter.mailer, "smtp_configured", lambda db: False)
    sent = patch_send(monkeypatch, True)

    await alerter.retry_unnotified(state)
    assert sent == []


async def test_retry_unnotified_age_guard_skips_young_rows(tmp_path, monkeypatch):
    """本轮刚触发的告警（触发邮件可能尚在途中的后台任务里）不当场补发——防 §8 双发。"""
    state = make_state(tmp_path)
    server = make_server(state)
    monkeypatch.setattr(alerter.mailer, "smtp_configured", lambda db: True)
    sent = patch_send(monkeypatch, True)
    now = datetime.now(timezone.utc)
    a_old = models.create_alert(
        state.db, server_id=server["id"], type_="offline",
        message="旧的待补发", triggered_at=(now - timedelta(hours=1)).isoformat(timespec="seconds"))
    a_young = models.create_alert(
        state.db, server_id=server["id"], type_="traffic_warn",
        message="刚触发", triggered_at=now.isoformat(timespec="seconds"))

    await alerter.retry_unnotified(state)

    assert len(sent) == 1 and "旧的待补发" in sent[0][1]
    assert state.db.query_one("SELECT notified FROM alerts WHERE id=?", (a_old,))["notified"] == 1
    assert state.db.query_one("SELECT notified FROM alerts WHERE id=?", (a_young,))["notified"] == 0
