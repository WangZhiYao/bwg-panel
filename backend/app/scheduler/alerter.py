"""告警状态机（规格 §8）：采样后检查触发/恢复；邮件异步发送不阻塞采样。

offline 去抖在内存（state.offline_since）：进程重启只损失去抖窗口（迟一轮告警），
其余状态全在 alerts 表（active 查询），重启安全。
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app import models, mailer
from app.defaults import DEFAULTS

logger = logging.getLogger(__name__)

OFFLINE_DEBOUNCE_SECONDS = 300     # 掉线持续 5 分钟才告警（重启窗口不误报）
THROTTLE_SUPPRESS_SECONDS = 7200   # cpu_throttle 官方约 2 小时自动重置：窗口内不重复
COLLECT_ERROR_THRESHOLD = 3        # 连续 3 轮采集失败（≈15 分钟）

TYPE_LABELS = {
    "offline": "掉线",
    "traffic_warn": "流量预警",
    "traffic_critical": "流量超限预警",
    "cpu_throttle": "CPU 节流",
    "collect_error": "采集失败",
    "email_error": "邮件通道故障",
}

# 后台发信任务的强引用集合：asyncio 仅弱引用裸任务，不持有会被 GC 中途取消
_BG_TASKS: set[asyncio.Task] = set()


def _fire_and_forget(coro) -> None:
    """提交 fire-and-forget 发信任务：强引用防 GC + 异常落日志（否则不可见）。"""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)

    def _log_exc(t: asyncio.Task) -> None:
        if not t.cancelled() and t.exception() is not None:
            logger.error("后台邮件任务异常", exc_info=t.exception())

    task.add_done_callback(_log_exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


async def check_server(state, server: dict, sample: dict, *, now: float | None = None) -> None:
    """采样成功后的检查：offline / traffic_warn / traffic_critical / cpu_throttle。"""
    now = time.time() if now is None else now
    sid = server["id"]
    status = sample["status"]

    # offline：去抖 5 分钟（内存窗口），running 即恢复
    if status == "running":
        state.offline_since.pop(sid, None)
        act = models.active_alert(state.db, sid, "offline")
        if act:
            await _resolve(state, server, act)
    else:
        since = state.offline_since.get(sid)
        if since is None:
            state.offline_since[sid] = now
        elif now - since >= OFFLINE_DEBOUNCE_SECONDS:
            if models.active_alert(state.db, sid, "offline") is None:
                await _trigger(state, server, "offline",
                               f"服务器 {server['name']} 已掉线超过 5 分钟（当前状态：{status}）")

    # traffic：quota=0 是「档案未刷新」哨兵，跳过（M4 交接要点）
    used = sample["data_counter"]
    quota = (
        int(server["plan_monthly_data"] * float(server["monthly_data_multiplier"] or 1))
        if server.get("plan_monthly_data") is not None else 0
    )
    if used is not None and quota > 0:
        await _check_traffic(state, server, used / quota, used, quota)

    if sample["cpu_throttled"]:
        await _check_throttle(state, server, now=now)


async def _check_traffic(state, server: dict, ratio: float, used: int, quota: int) -> None:
    warn = float(models.get_setting(state.db, "threshold_warn", DEFAULTS["threshold_warn"]))
    critical = float(models.get_setting(state.db, "threshold_critical", DEFAULTS["threshold_critical"]))
    detail = f"已用 {_human_bytes(used)} / 配额 {_human_bytes(quota)}"
    for type_, threshold in (("traffic_critical", critical), ("traffic_warn", warn)):
        act = models.active_alert(state.db, server["id"], type_)
        if ratio >= threshold and act is None:
            tail = "，接近配额上限" if type_ == "traffic_critical" else ""
            await _trigger(state, server, type_,
                           f"服务器 {server['name']} 流量用量已达 {ratio * 100:.1f}%，{detail}{tail}")
        elif ratio < threshold and act is not None:
            await _resolve(state, server, act)


async def _check_throttle(state, server: dict, *, now: float) -> None:
    """一次性告警：插入即解决；2 小时抑制窗口内不重复（now 为注入时钟，便于测试）。"""
    last = models.last_throttle_alert(state.db, server["id"])
    if last is not None:
        age = now - datetime.fromisoformat(last["triggered_at"]).timestamp()
        if age < THROTTLE_SUPPRESS_SECONDS:
            return
    await _trigger(state, server, "cpu_throttle",
                   f"服务器 {server['name']} CPU 被节流（官方约 2 小时自动解除）",
                   one_shot=True)


async def check_collect(state, server: dict, ok: bool) -> None:
    """采样成败后维护 collect_error（连续 3 轮失败触发，任意成功恢复）。"""
    act = models.active_alert(state.db, server["id"], "collect_error")
    if not ok:
        if act is None and state.consecutive_failures.get(server["id"], 0) >= COLLECT_ERROR_THRESHOLD:
            await _trigger(state, server, "collect_error",
                           f"服务器 {server['name']} 连续 {COLLECT_ERROR_THRESHOLD} 轮采样失败"
                           "（KiwiVM 不可达或凭证失效）")
    elif act:
        await _resolve(state, server, act)


async def _trigger(state, server: dict, type_: str, message: str, *, one_shot: bool = False) -> None:
    ts = _now_iso()
    alert_id = models.create_alert(state.db, server_id=server["id"], type_=type_,
                                   message=message, triggered_at=ts, resolved=one_shot)
    logger.warning("告警触发 %s %s：%s", server["name"], type_, message)
    _fire_and_forget(_send_and_track(
        state, server,
        subject=f"[BWG面板] {TYPE_LABELS[type_]}：{server['name']}",
        body=f"{message}\n\n触发时间（UTC）：{ts}\n\n—— BWG 面板自动告警",
        alert_id=None if one_shot else alert_id,
    ))


async def _resolve(state, server: dict, alert: dict) -> None:
    ts = _now_iso()
    models.resolve_alert(state.db, alert["id"], ts)
    logger.info("告警恢复 %s %s", server["name"], alert["type"])
    _fire_and_forget(_send_and_track(
        state, server,
        subject=f"[BWG面板] 已恢复：{TYPE_LABELS[alert['type']]}：{server['name']}",
        body=f"以下告警已恢复：\n{alert['message']}\n\n恢复时间（UTC）：{ts}\n\n—— BWG 面板自动告警",
        alert_id=None,
    ))


async def _send_and_track(state, server: dict, *, subject: str, body: str,
                          alert_id: int | None) -> None:
    """发送 + 记账：成功 → notified=1 并解除 email_error；失败 → 记 email_error。
    未配置 SMTP → 静默返回（notified 保持 0，配置完成后由 retry_unnotified 补发）。"""
    sent = await mailer.send_mail(state.db, subject, body)
    if sent is None:
        return
    if sent:
        if alert_id is not None:
            models.mark_notified(state.db, alert_id)
        act = models.active_alert(state.db, server["id"], "email_error")
        if act:  # 任一封成功即恢复（§8；email_error 自身不发恢复邮件）
            models.resolve_alert(state.db, act["id"], _now_iso())
        return
    if models.active_alert(state.db, server["id"], "email_error") is None:
        models.create_alert(state.db, server_id=server["id"], type_="email_error",
                            message=f"告警邮件发送失败：「{subject}」未送出，请检查 SMTP 设置",
                            triggered_at=_now_iso())


async def retry_unnotified(state) -> None:
    """每轮采样末尾补发：未解决且 notified=0 的告警（SMTP 恢复/配置后自动补齐）。

    防双发（§8 同一告警只发一封触发邮件）：本轮刚触发的告警跳过一个采样间隔——
    其 fire-and-forget 触发邮件可能仍卡在 SMTP 握手里（notified 尚为 0），此时补发
    会与在途邮件撞车造成同一告警两封；宽限一轮后仍未落地（发送失败/未配置）的，
    下一轮照常补发。
    """
    if not mailer.smtp_configured(state.db):
        return
    grace = float(models.get_setting(state.db, "sample_interval_seconds",
                                      DEFAULTS["sample_interval_seconds"]))
    cutoff = time.time() - grace
    rows = models.unnotified_alerts(state.db)
    if not rows:
        return
    servers = {s["id"]: s for s in models.list_servers(state.db)}
    for row in rows:
        if datetime.fromisoformat(row["triggered_at"]).timestamp() > cutoff:
            continue  # 刚触发不足一轮：给在途触发邮件落地时间（防双发）
        server = servers.get(row["server_id"])
        if server is None:
            continue
        await _send_and_track(
            state, server,
            subject=f"[BWG面板] {TYPE_LABELS.get(row['type'], row['type'])}：{server['name']}",
            body=(f"{row['message']}\n\n触发时间（UTC）：{row['triggered_at']}\n\n"
                  "—— BWG 面板自动告警（补发）"),
            alert_id=row["id"],
        )
