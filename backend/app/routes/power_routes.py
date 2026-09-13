"""电源管理：POST /api/servers/{id}/power。kill 需强确认（昵称，规格 §9）；全程写 ops_log。"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import models
from app.kiwivm.client import KiwiVMError
from app.routes.servers_routes import public_server
from app.scheduler.sampler import sample_one
from app.state import AppState, get_state, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["power"],
                   dependencies=[Depends(require_auth)])

POWER_ACTIONS = ("start", "stop", "restart", "kill")


class PowerBody(BaseModel):
    action: str
    confirm_name: str | None = None


@router.post("/{server_id}/power")
async def power_server(server_id: int, body: PowerBody,
                       state: AppState = Depends(get_state)):
    server = models.get_server(state.db, server_id)
    if not server:
        raise HTTPException(404, detail={"error": "server_not_found", "message": "服务器不存在"})
    if body.action not in POWER_ACTIONS:
        raise HTTPException(400, detail={"error": "invalid_action",
                                         "message": "action 仅支持 start/stop/restart/kill"})
    if body.action == "kill":
        if not body.confirm_name or body.confirm_name.strip() != server["name"]:
            raise HTTPException(400, detail={
                "error": "confirm_mismatch",
                "message": "强制断电需输入服务器昵称确认",
            })

    client = state.clients.for_server(server)
    try:
        data = await client.power(body.action)
    except KiwiVMError as e:
        models.log_op(state.db, server_id=server_id, action=f"power.{body.action}",
                      result="error", detail={"code": e.code, "message": e.message})
        raise HTTPException(502, detail={"error": "kiwivm",
                                         "message": "KiwiVM 调用失败，请稍后重试",
                                         "detail": e.code})
    models.log_op(state.db, server_id=server_id, action=f"power.{body.action}",
                  result="ok", detail={"response": data})
    # 操作成功后立即采一次样让状态尽快反映（失败容忍：调度器下轮兜底）。
    # 与 sample_all 同款护栏：sample_one 只吞 KiwiVMError，这里的意外异常不应
    # 把"已成功执行的电源操作"变成 500 诱导重试。
    try:
        await sample_one(state, server)
    except Exception:  # noqa: BLE001 —— 审计已落库，操作已生效，仅记录
        logger.exception("power 操作后的即时采样失败 server_id=%s", server_id)
    return public_server(state, models.get_server(state.db, server_id))
