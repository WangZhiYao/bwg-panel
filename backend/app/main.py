"""FastAPI 装配：lifespan（种子密码/mock 服务器/调度器/共享连接池）+ 路由 + 静态托管占位。"""

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import auth, models
from app.db import Database
from app.defaults import DEFAULTS
from app.kiwivm.client import KiwiVMClient
from app.routes import alerts_routes, auth_routes, meta_routes, power_routes, servers_routes, settings_routes, snapshots_routes
from app.state import AppState, ClientFactory
from app.version import VERSION

_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """SPA 深链回退：非 /api 的未知路径返回 index.html（/trends、/login 刷新可用）。"""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Starlette 对未命中文件抛 HTTPException(404) 而非返回 404 响应；
            # path 经 normpath 处理不可靠，用 scope 里的完整请求路径判断 /api
            if exc.status_code == 404 and not scope["path"].startswith("/api/"):
                return await super().get_response("index.html", scope)
            raise


def create_app(
    *,
    mock: bool = False,
    start_scheduler: bool = True,
    db_path: str | None = None,
    secret_key: str | None = None,
    admin_password: str | None = None,
    cookie_secure: bool | None = None,
) -> FastAPI:
    if db_path is None or secret_key is None:
        # 完整注入（测试）则不读 .env：既保测试隔离，也避免宿主环境泄漏
        from app.config import load_config
        cfg = load_config(mock=mock)
        db_path = db_path or cfg.db_path
        secret_key = secret_key or cfg.secret_key
        admin_password = admin_password or cfg.admin_password
        if cookie_secure is None:
            cookie_secure = cfg.cookie_secure
    if cookie_secure is None:
        cookie_secure = False

    db = Database(db_path)
    shared_http = None if mock else httpx.AsyncClient(timeout=KiwiVMClient.TIMEOUT)
    state = AppState(
        db=db,
        sessions=auth.SessionManager(secret_key),
        clients=ClientFactory(mock=mock, http=shared_http),
        mock=mock,
        login_limiter=auth.LoginRateLimiter(),
        cookie_secure=cookie_secure,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        try:
            _bootstrap_admin_password(state, admin_password)
            if mock and not models.list_servers(db):
                a = models.create_server(db, name="Mock-A", veid="9000001", api_key="mock")
                b = models.create_server(db, name="Mock-B", veid="9000002", api_key="mock")
                _seed_mock_alerts(db, a["id"], b["id"])
            if start_scheduler:
                scheduler = _start_scheduler(state)
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)
            from app.scheduler import alerter as _alerter
            if _alerter._BG_TASKS:  # 排空在途邮件任务，防 db.close 后写库报错
                await asyncio.wait(set(_alerter._BG_TASKS), timeout=2)
            if shared_http is not None:
                await shared_http.aclose()
            db.close()

    app = FastAPI(title="BWG Panel", version=VERSION, lifespan=lifespan)
    app.state.state = state

    # 注册在 Starlette 基类上：未命中路由的 404 抛的是基类而非 fastapi.HTTPException
    @app.exception_handler(StarletteHTTPException)
    async def flat_error_handler(request, exc: StarletteHTTPException):
        content = exc.detail if isinstance(exc.detail, dict) else {
            "error": "error", "message": str(exc.detail),
        }
        return JSONResponse(status_code=exc.status_code, content=content)

    # 422 扁平化：T10 登录路由落地后补触发测试
    @app.exception_handler(RequestValidationError)
    async def flat_validation_error(request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "请求参数校验失败",
                "detail": [
                    {"loc": ".".join(map(str, e.get("loc", []))), "msg": e.get("msg"), "type": e.get("type")}
                    for e in exc.errors()[:5]
                ],
            },
        )

    app.include_router(meta_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(alerts_routes.router)
    app.include_router(servers_routes.router)
    app.include_router(power_routes.router)
    app.include_router(snapshots_routes.router)
    app.include_router(settings_routes.router)

    if _FRONTEND_DIST.exists():
        app.mount("/", SPAStaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
    else:
        @app.get("/", include_in_schema=False)
        async def frontend_placeholder():
            return JSONResponse(
                status_code=503,
                content={
                    "error": "frontend_not_built",
                    "message": "前端尚未构建：请执行 cd frontend && npm run build（M2 提供），"
                               "当前可用 /docs 与 REST API",
                },
            )

    return app


def _seed_mock_alerts(db, a_id: int, b_id: int) -> None:
    """mock 演示告警：1 条未解决（铃铛/横幅即有内容）+ 2 条已恢复历史。"""
    from datetime import datetime, timedelta, timezone

    def iso(days_ago: float) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")

    aid = models.create_alert(
        db, server_id=a_id, type_="traffic_warn",
        message="服务器 Mock-A 流量用量已达 85.0%，已用 850.0 GB / 配额 1000.0 GB",
        triggered_at=iso(0.2),
    )
    models.mark_notified(db, aid)
    off = models.create_alert(
        db, server_id=b_id, type_="offline",
        message="服务器 Mock-B 已掉线超过 5 分钟（当前状态：stopped）",
        triggered_at=iso(3.1),
    )
    models.resolve_alert(db, off, iso(3.0))
    models.mark_notified(db, off)
    ce = models.create_alert(
        db, server_id=b_id, type_="collect_error",
        message="服务器 Mock-B 连续 3 轮采样失败（KiwiVM 不可达或凭证失效）",
        triggered_at=iso(1.5),
    )
    models.resolve_alert(db, ce, iso(1.4))
    models.mark_notified(db, ce)


def _bootstrap_admin_password(state: AppState, admin_password: str | None) -> None:
    if models.get_setting(state.db, "admin_password_hash"):
        return
    password = admin_password or secrets.token_urlsafe(12)
    if not admin_password:
        print(f"[bwg-panel] 已生成初始管理员密码：{password}（仅显示一次，请妥善保存）")
    models.set_setting(state.db, "admin_password_hash", auth.hash_password(password))


def _start_scheduler(state: AppState):
    from datetime import datetime, timezone

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from app.scheduler.sampler import sample_all

    interval = int(models.get_setting(state.db, "sample_interval_seconds")
                   or DEFAULTS["sample_interval_seconds"])

    async def sampler_job() -> None:  # 必须是协程函数：AsyncIOScheduler 才会 await
        await sample_all(state)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        sampler_job, "interval", seconds=interval, id="sampler",
        next_run_time=datetime.now(tz=timezone.utc),  # 启动即先采一轮
    )
    scheduler.start()
    state.scheduler = scheduler  # M4：settings 修改采样间隔后热生效
    return scheduler
