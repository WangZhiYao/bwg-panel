from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import mailer, models
from app.defaults import DEFAULTS
from app.state import AppState, get_state, require_auth

router = APIRouter(prefix="/api/settings", tags=["settings"],
                   dependencies=[Depends(require_auth)])


def public_settings(db) -> dict:
    """DB 值叠加默认（缺省键不落库，读取时补默认）；smtp_pass 永不外泄。"""
    out = {key: models.get_setting(db, key, default) for key, default in DEFAULTS.items()}
    out["smtp_pass_set"] = bool(models.get_setting(db, "smtp_pass", ""))  # UI：是否已存密码
    return out


class SettingsBody(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str | None = None
    smtp_to: list[str] | None = None
    threshold_warn: float | None = None
    threshold_critical: float | None = None
    threshold_disk: float | None = None
    threshold_mem: float | None = None
    sample_interval_seconds: int | None = None
    timezone: str | None = None


@router.get("")
async def get_settings(state: AppState = Depends(get_state)):
    return public_settings(state.db)


@router.put("")
async def put_settings(body: SettingsBody, state: AppState = Depends(get_state)):
    """部分更新 settings。

    smtp_pass 三态：省略 = 保留；显式空串/null = 清除（切换免认证 SMTP 用）；
    非空 = 更新。前端表单空白即省略（undefined），界面语义仍是「留空=不修改」。
    """
    updates = body.model_dump(exclude_unset=True)
    current = public_settings(state.db)

    # smtp_pass 三态：省略=保留；显式空串/null=清除（切换免认证 SMTP）；非空=更新。
    # 前端表单空白即省略（undefined），界面语义仍是"留空=不修改"。
    if "smtp_pass" in updates and not updates["smtp_pass"]:
        updates["smtp_pass"] = ""
    updates = {k: v for k, v in updates.items() if v is not None}

    warn = updates.get("threshold_warn")
    critical = updates.get("threshold_critical")
    eff_warn = warn if warn is not None else current["threshold_warn"]
    eff_critical = critical if critical is not None else current["threshold_critical"]
    if not (0 < eff_warn < eff_critical < 1):
        raise HTTPException(400, detail={
            "error": "invalid_threshold",
            "message": "阈值需满足 0 < 预警 < 超限 < 1（如 0.8 与 0.95）"})

    for key in ("threshold_disk", "threshold_mem"):
        v = updates.get(key)
        if v is not None and not 0.5 <= v <= 0.99:
            raise HTTPException(400, detail={
                "error": "invalid_threshold",
                "message": "磁盘/内存阈值需在 50%–99% 之间"})

    interval = updates.get("sample_interval_seconds")
    if interval is not None and not 60 <= interval <= 3600:
        raise HTTPException(400, detail={
            "error": "invalid_interval", "message": "采样间隔仅支持 60–3600 秒"})

    port = updates.get("smtp_port")
    if port is not None and not 1 <= port <= 65535:
        raise HTTPException(400, detail={
            "error": "invalid_port", "message": "SMTP 端口无效"})

    tz = updates.get("timezone")
    if tz is not None:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(400, detail={
                "error": "invalid_timezone", "message": "无法识别的时区（如 Asia/Shanghai）"})

    to = updates.get("smtp_to")
    if to is not None:
        updates["smtp_to"] = [x.strip() for x in to if x and x.strip()]

    for key, value in updates.items():
        models.set_setting(state.db, key, value)

    # 采样间隔热生效（调度器就绪时直接改触发器，无需重启）
    if interval is not None and state.scheduler is not None:
        state.scheduler.reschedule_job("sampler", trigger="interval", seconds=interval)

    return public_settings(state.db)


@router.post("/test-email")
async def test_email(state: AppState = Depends(get_state)):
    """立即发一封测试邮件（同步等待结果，前端按钮 loading）。"""
    if not mailer.smtp_configured(state.db):
        raise HTTPException(400, detail={
            "error": "smtp_not_configured",
            "message": "请先填写并保存 SMTP 设置（主机/账号/收件人）"})
    sent = await mailer.send_mail(state.db, "BWG 面板测试邮件",
                                  "这是一封测试邮件：SMTP 通道工作正常。")
    if sent is not True:
        raise HTTPException(502, detail={
            "error": "email_send_failed",
            "message": "邮件发送失败，请检查 SMTP 主机/端口/账号/授权码"})
    return {"ok": True}
