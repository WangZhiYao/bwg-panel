import email
import email.policy
import smtplib

import pytest

from app import mailer, models
from app.db import Database


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "m.db"))
    yield d
    d.close()


def _configure(db, **over):
    values = {"smtp_host": "smtp.example.com", "smtp_port": 465,
              "smtp_user": "panel@example.com", "smtp_pass": "secret",
              "smtp_from": "", "smtp_to": ["me@example.com"]}
    values.update(over)
    for k, v in values.items():
        if v != "":
            models.set_setting(db, k, v)


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.calls = []
        _FakeSMTP.instances.append(self)

    def ehlo(self): self.calls.append("ehlo")
    def has_extn(self, name): return False
    def starttls(self): self.calls.append("starttls")
    def login(self, user, pw): self.calls.append(("login", user, pw))
    def sendmail(self, frm, to, text): self.calls.append(("sendmail", frm, to, text))
    def quit(self): self.calls.append("quit")


def test_load_smtp_settings_requires_minimum(db):
    assert mailer.load_smtp_settings(db) is None          # host/user/to 缺一不可
    _configure(db)
    got = mailer.load_smtp_settings(db)
    assert got["host"] == "smtp.example.com"
    assert got["from"] == "panel@example.com"             # 空 from 回落 user
    assert got["to"] == ["me@example.com"]


def test_smtp_configured_flag(db):
    assert mailer.smtp_configured(db) is False
    _configure(db)
    assert mailer.smtp_configured(db) is True


async def test_send_mail_unconfigured_returns_none(db):
    assert await mailer.send_mail(db, "s", "b") is None


async def test_send_mail_ssl_port_uses_smtp_ssl(db, monkeypatch):
    _configure(db)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    assert await mailer.send_mail(db, "测试主题", "测试正文") is True
    inst = _FakeSMTP.instances[-1]
    assert inst.port == 465
    sent = [c for c in inst.calls if c[0] == "sendmail"][0]
    assert sent[1] == "panel@example.com"
    assert sent[2] == ["me@example.com"]
    # MIME 对非 ASCII 做 base64/RFC2047 编码（smtplib 仅接受 ASCII str），解码后校验内容
    m = email.message_from_string(sent[3], policy=email.policy.default)
    assert m["subject"] == "测试主题"
    assert m.get_payload(decode=True) == "测试正文".encode("utf-8")


async def test_send_mail_starttls_on_other_port(db, monkeypatch):
    _configure(db, smtp_port=587)

    class _TLS(_FakeSMTP):
        def has_extn(self, name): return name == "starttls"

    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", _TLS)
    assert await mailer.send_mail(db, "s", "b") is True
    inst = _TLS.instances[-1]
    assert "starttls" in inst.calls
    assert ("login", "panel@example.com", "secret") in inst.calls


async def test_send_mail_retries_once_then_false(db, monkeypatch):
    _configure(db)
    calls = {"n": 0}

    class _Boom:
        def __init__(self, *a, **k): pass
        def ehlo(self): pass
        def has_extn(self, n): return False
        def login(self, u, p): pass
        def sendmail(self, f, t, s): calls["n"] += 1; raise OSError("boom")
        def quit(self): pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", _Boom)
    assert await mailer.send_mail(db, "s", "b") is False
    assert calls["n"] == 2  # 失败后重试 1 次（§8）
