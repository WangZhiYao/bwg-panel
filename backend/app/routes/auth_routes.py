from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import auth, models
from app.state import AppState, get_state, require_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


@router.post("/login")
async def login(body: LoginBody, request: Request, state: AppState = Depends(get_state)):
    # 生产经 Caddy 反代：FORWARDED_ALLOW_IPS 信任网关后，request.client.host 已是真实客户端 IP
    # （uvicorn 从 X-Forwarded-For 最右侧取首个非受信跳，客户端伪造头部无效）
    ip = request.client.host if request.client else "unknown"
    if state.login_limiter.blocked(ip):
        raise HTTPException(429, detail={"error": "rate_limited", "message": "尝试过于频繁，请 1 分钟后再试"})
    stored = models.get_setting(state.db, "admin_password_hash")
    if not stored or not auth.verify_password(body.password, stored):
        state.login_limiter.record(ip)
        raise HTTPException(401, detail={"error": "bad_credentials", "message": "密码错误"})
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        auth.SESSION_COOKIE, state.sessions.issue(),
        max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
        secure=state.cookie_secure,  # 反代 HTTPS 部署经 .env COOKIE_SECURE=1 开启（规格 §9）
    )
    return resp


@router.post("/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


@router.get("/me", dependencies=[Depends(require_auth)])
async def me():
    return {"user": "admin"}
