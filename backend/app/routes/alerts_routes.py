"""告警列表：?active=1 只看未解决且未确认（铃铛/横幅口径）；默认全部（触发时间倒序，至多 200 条）。"""

from fastapi import APIRouter, Depends, HTTPException

from app import models
from app.state import AppState, get_state, require_auth

router = APIRouter(prefix="/api/alerts", tags=["alerts"],
                   dependencies=[Depends(require_auth)])


@router.get("")
async def list_alerts(active: int = 0, state: AppState = Depends(get_state)):
    rows = models.list_alerts(state.db, active_only=bool(active))
    names = {s["id"]: s["name"] for s in models.list_servers(state.db)}
    return [
        {
            "id": r["id"],
            "server_id": r["server_id"],
            "server_name": names.get(r["server_id"], f"#{r['server_id']}"),
            "type": r["type"],
            "message": r["message"],
            "triggered_at": r["triggered_at"],
            "resolved_at": r["resolved_at"],
            "notified": bool(r["notified"]),
            "acknowledged": bool(r["acknowledged"]),
        }
        for r in rows
    ]


@router.post("/{alert_id}/ack")
async def ack_alert(alert_id: int, state: AppState = Depends(get_state)):
    """标记已读：不再计入铃铛角标与总览横幅（问题恢复后再次触发会作为新告警重新提醒）。幂等。"""
    if models.get_alert(state.db, alert_id) is None:
        raise HTTPException(404, detail={"error": "alert_not_found", "message": "告警不存在"})
    models.ack_alert(state.db, alert_id)
    return {"ok": True}
