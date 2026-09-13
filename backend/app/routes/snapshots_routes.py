"""快照管理：列表/创建/删除/恢复。restore 需强确认（昵称，规格 §9）；全程写 ops_log。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import models
from app.kiwivm.client import KiwiVMError
from app.state import AppState, get_state, require_auth

router = APIRouter(prefix="/api/servers", tags=["snapshots"],
                   dependencies=[Depends(require_auth)])


class SnapshotCreateBody(BaseModel):
    description: str | None = None


class SnapshotRestoreBody(BaseModel):
    confirm_name: str | None = None


def _server_or_404(state: AppState, server_id: int) -> dict:
    server = models.get_server(state.db, server_id)
    if not server:
        raise HTTPException(404, detail={"error": "server_not_found", "message": "服务器不存在"})
    return server


def _confirm_or_400(server: dict, confirm_name: str | None) -> None:
    if not confirm_name or confirm_name.strip() != server["name"]:
        raise HTTPException(400, detail={
            "error": "confirm_mismatch",
            "message": "恢复快照需输入服务器昵称确认",
        })


@router.get("/{server_id}/snapshots")
async def list_snapshots(server_id: int, state: AppState = Depends(get_state)):
    server = _server_or_404(state, server_id)
    client = state.clients.for_server(server)
    try:
        data = await client.snapshot_list()
    except KiwiVMError as e:
        raise HTTPException(502, detail={"error": "kiwivm",
                                         "message": "KiwiVM 调用失败，请稍后重试",
                                         "detail": e.code})
    return {"snapshots": data.get("snapshots", [])}


@router.post("/{server_id}/snapshots")
async def create_snapshot(server_id: int, body: SnapshotCreateBody,
                          state: AppState = Depends(get_state)):
    server = _server_or_404(state, server_id)
    client = state.clients.for_server(server)
    try:
        data = await client.snapshot_create((body.description or "").strip())
    except KiwiVMError as e:
        models.log_op(state.db, server_id=server_id, action="snapshot.create",
                      result="error", detail={"code": e.code, "message": e.message})
        raise HTTPException(502, detail={"error": "kiwivm",
                                         "message": "KiwiVM 调用失败，请稍后重试",
                                         "detail": e.code})
    models.log_op(state.db, server_id=server_id, action="snapshot.create",
                  result="ok", detail={"fileName": data.get("fileName")})
    return data


@router.delete("/{server_id}/snapshots/{file_name}", status_code=204)
async def delete_snapshot(server_id: int, file_name: str,
                          state: AppState = Depends(get_state)):
    server = _server_or_404(state, server_id)
    client = state.clients.for_server(server)
    try:
        await client.snapshot_delete(file_name)
    except KiwiVMError as e:
        models.log_op(state.db, server_id=server_id, action="snapshot.delete",
                      result="error", detail={"fileName": file_name,
                                              "code": e.code, "message": e.message})
        raise HTTPException(502, detail={"error": "kiwivm",
                                         "message": "KiwiVM 调用失败，请稍后重试",
                                         "detail": e.code})
    models.log_op(state.db, server_id=server_id, action="snapshot.delete",
                  result="ok", detail={"fileName": file_name})
    return None


@router.post("/{server_id}/snapshots/{file_name}/restore")
async def restore_snapshot(server_id: int, file_name: str, body: SnapshotRestoreBody,
                           state: AppState = Depends(get_state)):
    server = _server_or_404(state, server_id)
    _confirm_or_400(server, body.confirm_name)
    client = state.clients.for_server(server)
    try:
        await client.snapshot_restore(file_name)
    except KiwiVMError as e:
        models.log_op(state.db, server_id=server_id, action="snapshot.restore",
                      result="error", detail={"fileName": file_name,
                                              "code": e.code, "message": e.message})
        raise HTTPException(502, detail={"error": "kiwivm",
                                         "message": "KiwiVM 调用失败，请稍后重试",
                                         "detail": e.code})
    models.log_op(state.db, server_id=server_id, action="snapshot.restore",
                  result="ok", detail={"fileName": file_name})
    return {"ok": True}
