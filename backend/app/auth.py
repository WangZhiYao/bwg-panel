"""认证：bcrypt 密码 + itsdangerous 签名 Cookie 会话 + 登录限速（规格 §9）。

# 注：bcrypt 限制密码 72 字节，两侧统一截断；token 无法单独撤销，轮换 SECRET_KEY 即全部失效
"""

import time
from collections import defaultdict

import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature

SESSION_COOKIE = "bwg_session"
SESSION_TTL = 7 * 86400  # 7 天


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]  # bcrypt 上限 72 字节，两侧统一截断
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    pw = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pw, hashed.encode("ascii"))
    except ValueError:
        return False


class SessionManager:
    def __init__(self, secret_key: str):
        self._serializer = URLSafeTimedSerializer(secret_key, salt="bwg-session")

    def issue(self) -> str:
        return self._serializer.dumps({"sub": "admin"})

    def verify(self, token: str, max_age: int = SESSION_TTL) -> bool:
        try:
            data = self._serializer.loads(token, max_age=max_age)
        except BadSignature:
            return False
        return data.get("sub") == "admin"


class LoginRateLimiter:
    """内存版每 IP 滑动窗口：window 秒内最多 max_attempts 次。"""

    def __init__(self, max_attempts: int = 5, window: float = 60.0,
                 clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window = window
        self._clock = clock
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def blocked(self, ip: str) -> bool:
        """窗口内失败次数是否已达上限。"""
        now = self._clock()
        hits = [t for t in self._attempts[ip] if now - t < self.window]
        self._attempts[ip] = hits
        return len(hits) >= self.max_attempts

    def record(self, ip: str) -> None:
        """记一次失败尝试。"""
        now = self._clock()
        hits = [t for t in self._attempts[ip] if now - t < self.window]
        hits.append(now)
        self._attempts[ip] = hits
