"""运行时共享状态与 FastAPI 依赖。"""

from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import HTTPException, Request

from app.auth import LoginRateLimiter, SessionManager
from app.db import Database
from app.kiwivm.client import KiwiVMClient
from app.kiwivm.mock import MockKiwiVMClient


class ClientFactory:
    """按当前模式为某台服务器构造客户端；真实模式共享一个连接池（lifespan 统一关闭）。"""

    def __init__(self, mock: bool, http: httpx.AsyncClient | None = None):
        self.mock = mock
        self._http = http

    def for_server(self, server: dict) -> Any:
        if self.mock:
            return MockKiwiVMClient(server["veid"])
        return KiwiVMClient(server["veid"], server["api_key"], http=self._http)


@dataclass
class AppState:
    db: Database
    sessions: SessionManager
    clients: ClientFactory
    mock: bool
    login_limiter: LoginRateLimiter
    cookie_secure: bool = False
    # 运行时缓存（M1 仅展示；M4 告警会消费 consecutive_failures）
    last_refresh: dict[int, float] = field(default_factory=dict)
    rate_limit_cache: dict | None = None
    rate_limit_at: float | None = None
    last_sample_at: float | None = None
    consecutive_failures: dict[int, int] = field(default_factory=dict)
    offline_since: dict[int, float] = field(default_factory=dict)  # M4 offline 去抖窗口
    scheduler: object | None = None  # M4：采样间隔热生效（settings PUT 后 reschedule）


def get_state(request: Request) -> AppState:
    return request.app.state.state


async def require_auth(request: Request) -> None:
    from app.auth import SESSION_COOKIE
    state: AppState = request.app.state.state
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not state.sessions.verify(token):
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "未登录或会话过期"},
        )
