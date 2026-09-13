from app.auth import (
    LoginRateLimiter, SessionManager, hash_password, verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h) is True
    assert verify_password("wrong", h) is False
    assert verify_password("s3cret", "not-a-hash") is False  # 非法哈希不抛异常


def test_session_issue_and_verify():
    sm = SessionManager("test-secret")
    token = sm.issue()
    assert sm.verify(token) is True
    assert sm.verify("tampered-token") is False


def test_session_expired():
    sm = SessionManager("test-secret")
    token = sm.issue()
    assert sm.verify(token, max_age=-1) is False  # 立即过期


def test_login_rate_limiter():
    limiter = LoginRateLimiter(max_attempts=5, window=60.0)
    ip = "1.2.3.4"
    for _ in range(5):
        assert limiter.blocked(ip) is False
        limiter.record(ip)
    assert limiter.blocked(ip) is True           # 达上限
    assert limiter.blocked("5.6.7.8") is False   # 其他 IP 不受影响


def test_login_rate_limiter_window_reset():
    clock = {"t": 0.0}
    limiter = LoginRateLimiter(max_attempts=2, window=60.0, clock=lambda: clock["t"])
    ip = "1.2.3.4"
    limiter.record(ip); limiter.record(ip)
    assert limiter.blocked(ip) is True
    clock["t"] += 61.0                           # 窗口滑过
    assert limiter.blocked(ip) is False


def test_password_longer_than_72_bytes_roundtrip():
    long_pw = "x" * 100
    h = hash_password(long_pw)
    assert verify_password(long_pw, h) is True      # 不再抛 ValueError
    # 截断语义：前 72 字节相同即视为相同密码（"x"*100 与 "x"*100+"y" 的前 72 字节一致）
    assert verify_password("x" * 100 + "y", h) is True
