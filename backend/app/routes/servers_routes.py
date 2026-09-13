import json
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import models
from app.defaults import DEFAULTS
from app.kiwivm.client import KiwiVMError  # noqa: F401（refresh 错误语义保留引用）
from app.scheduler.sampler import sample_one
from app.state import AppState, get_state, require_auth

router = APIRouter(prefix="/api/servers", tags=["servers"],
                   dependencies=[Depends(require_auth)])

STALE_AFTER_SECONDS = 900  # 15 分钟无新采样视为过期（规格 §12）


class ServerCreateBody(BaseModel):
    name: str
    veid: str
    api_key: str


class ServerUpdateBody(BaseModel):
    name: str | None = None
    veid: str | None = None
    api_key: str | None = None


def public_server(state: AppState, server: dict) -> dict:
    """对外视图：绝不含 api_key（规格 §9）。"""
    latest = models.latest_sample(state.db, server["id"])
    multiplier = float(server.get("monthly_data_multiplier") or 1)
    quota = (
        int(server["plan_monthly_data"] * multiplier)
        if server.get("plan_monthly_data") is not None else 0
    )
    used = (
        latest["data_counter"]
        if latest and latest.get("data_counter") is not None else None
    )
    stale = True
    if latest:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest["ts"])).total_seconds()
        stale = age > STALE_AFTER_SECONDS
    return {
        "id": server["id"],
        "name": server["name"],
        "veid": server["veid"],
        "node_location": server["node_location"],
        "os": server["os"],
        "vm_type": server["vm_type"],
        "ip_addresses": json.loads(server["ip_addresses"]) if server.get("ip_addresses") else [],
        "plan_disk": server["plan_disk"],
        "plan_ram": server["plan_ram"],
        "plan_swap": server["plan_swap"],
        # quota=0 表示档案未刷新（未采样过），前端按未知处理
        "traffic": {"used": used, "quota": 0 if quota is None else quota, "next_reset": server.get("data_next_reset")},
        "latest": latest,
        "stale": stale,
    }


@router.get("")
async def list_servers(state: AppState = Depends(get_state)):
    return [public_server(state, s) for s in models.list_servers(state.db)]


@router.post("", status_code=201)
async def create_server(body: ServerCreateBody, state: AppState = Depends(get_state)):
    if not body.name.strip():
        raise HTTPException(400, detail={"error": "invalid_name", "message": "昵称不能为空"})
    if not body.veid.isdigit():
        raise HTTPException(400, detail={"error": "invalid_veid", "message": "veid 必须是数字"})
    if body.api_key is not None and not body.api_key:
        raise HTTPException(400, detail={"error": "invalid_api_key", "message": "api_key 不能为空"})
    if models.get_server_by_veid(state.db, body.veid):
        raise HTTPException(409, detail={"error": "veid_exists", "message": "该 veid 已存在"})
    server = models.create_server(
        state.db, name=body.name.strip(), veid=body.veid, api_key=body.api_key,
    )
    return public_server(state, server)


@router.patch("/{server_id}")
async def update_server(server_id: int, body: ServerUpdateBody,
                        state: AppState = Depends(get_state)):
    if not models.get_server(state.db, server_id):
        raise HTTPException(404, detail={"error": "server_not_found", "message": "服务器不存在"})
    if body.veid is not None:
        if not body.veid.isdigit():
            raise HTTPException(400, detail={"error": "invalid_veid", "message": "veid 必须是数字"})
        existing = models.get_server_by_veid(state.db, body.veid)
        if existing and existing["id"] != server_id:
            raise HTTPException(409, detail={"error": "veid_exists", "message": "该 veid 已存在"})
    if body.name is not None and not body.name.strip():
        raise HTTPException(400, detail={"error": "invalid_name", "message": "昵称不能为空"})
    if body.api_key is not None and not body.api_key:
        raise HTTPException(400, detail={"error": "invalid_api_key", "message": "api_key 不能为空"})
    server = models.update_server(
        state.db, server_id,
        name=body.name.strip() if body.name is not None else None,
        veid=body.veid, api_key=body.api_key,
    )
    return public_server(state, server)


@router.delete("/{server_id}", status_code=204)
async def delete_server(server_id: int, state: AppState = Depends(get_state)):
    if not models.delete_server(state.db, server_id):
        raise HTTPException(404, detail={"error": "server_not_found", "message": "服务器不存在"})


REFRESH_TTL_SECONDS = 60        # 页面即时刷新去重（规格 §7）
RATE_LIMIT_FLOOR = 50           # 15min 余量绝对下限（偏差说明见计划头部）
RATE_LIMIT_STALE_SECONDS = 900  # 点数缓存超过此年龄按未知处理（3× 默认采样间隔）


def _rate_limit_ok(state: AppState) -> bool:
    """点数未知/缓存陈旧 → 放行；已知且低于下限 → 拒绝。"""
    if (
        state.rate_limit_cache is None
        or state.rate_limit_at is None
        or time.time() - state.rate_limit_at > RATE_LIMIT_STALE_SECONDS
    ):
        return True
    return state.rate_limit_cache.get("remaining_points_15min", 10**9) >= RATE_LIMIT_FLOOR


@router.post("/{server_id}/refresh")
async def refresh_server(server_id: int, state: AppState = Depends(get_state)):
    server = models.get_server(state.db, server_id)
    if not server:
        raise HTTPException(404, detail={"error": "server_not_found", "message": "服务器不存在"})
    now = time.time()
    if now - state.last_refresh.get(server_id, 0) < REFRESH_TTL_SECONDS:
        raise HTTPException(429, detail={"error": "refresh_ttl", "message": "刷新过于频繁（60 秒内已刷新）"})
    if not _rate_limit_ok(state):
        raise HTTPException(429, detail={"error": "rate_limit_low", "message": "API 点数余量过低，已暂停即时刷新"})
    state.last_refresh[server_id] = now  # 乐观占位：await 前落锁，防并发双花
    ok = await sample_one(state, server)  # 失败时内部已计数且不落库（规格 §7）
    if not ok:
        state.last_refresh.pop(server_id, None)  # 失败不惩罚 TTL
        raise HTTPException(502, detail={"error": "kiwivm", "message": "KiwiVM 调用失败，请稍后重试"})
    server = models.get_server(state.db, server_id)
    return public_server(state, server)


HISTORY_RANGES = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}


@router.get("/{server_id}/history")
async def server_history(server_id: int, range: str = "24h",
                         state: AppState = Depends(get_state)):
    if range not in HISTORY_RANGES:
        raise HTTPException(
            400, detail={"error": "invalid_range", "message": "range 仅支持 24h/7d/30d"},
        )
    if not models.get_server(state.db, server_id):
        raise HTTPException(404, detail={"error": "server_not_found", "message": "服务器不存在"})
    since = (
        datetime.now(timezone.utc) - timedelta(seconds=HISTORY_RANGES[range])
    ).isoformat(timespec="seconds")
    tz_name = models.get_setting(state.db, "timezone", DEFAULTS["timezone"])
    return {
        "samples": models.samples_since(state.db, server_id, since),
        "daily_usage": models.daily_usage(state.db, server_id, since, tz_name),
    }
