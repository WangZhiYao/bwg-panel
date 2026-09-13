"""定时采样：成功写 samples + 刷新档案并喂给告警检查；失败计数转 collect_error。"""

import logging
import time
from datetime import datetime, timezone

from app import models
from app.kiwivm import mapping
from app.kiwivm.client import KiwiVMError
from app.scheduler import alerter

logger = logging.getLogger(__name__)


async def sample_all(state) -> None:
    servers = models.list_servers(state.db)
    for server in servers:
        try:
            await sample_one(state, server)
        except Exception:  # 单台意外失败不拖垮整轮（KiwiVMError 已在 sample_one 内处理）
            logger.exception("sample_one 意外失败 server_id=%s", server["id"])
    if servers:  # 每轮只对第一台查点数，缓存供 meta/降级判断（规格 §7/§13）
        try:
            rl = await state.clients.for_server(servers[0]).get_rate_limit_status()
            state.rate_limit_cache = rl
            state.rate_limit_at = time.time()
        except Exception:
            logger.exception("点数查询失败")
    await alerter.retry_unnotified(state)  # 每轮末尾补发未通知告警（规格 §8）


async def sample_one(state, server: dict) -> bool:
    """采样一台服务器。返回是否成功（调度器忽略返回值；refresh 路由用它报 502）。"""
    try:
        info = await state.clients.for_server(server).get_live_service_info()
    except KiwiVMError:
        # 网络级重试已在 KiwiVMClient._call 内完成（1 次）；
        # 这里只累计连续失败，失败轮次不落库（规格 §7）
        state.consecutive_failures[server["id"]] = (
            state.consecutive_failures.get(server["id"], 0) + 1
        )
        await alerter.check_collect(state, server, ok=False)
        return False
    state.consecutive_failures[server["id"]] = 0

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sample = mapping.sample_from_live(info)  # 落库与告检查同一条样本：存什么就查什么
    models.insert_sample(state.db, server_id=server["id"], ts=ts, **sample)
    # 档案刷新后回读：check_server 依据 server 档案里的配额算流量占比
    server = models.update_server(state.db, server["id"], profile=mapping.profile_from_info(info))
    state.last_sample_at = time.time()
    await alerter.check_collect(state, server, ok=True)
    await alerter.check_server(state, server, sample)
    return True
