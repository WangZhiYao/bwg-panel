"""SMTP 发信：标准库 smtplib 套 asyncio.to_thread（零新依赖，§8 异步不阻塞）。

端口约定：465 → SMTP_SSL；其余端口 EHLO 后服务器支持 STARTTLS 则升级；有密码则 login。
"""

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate

from app import models
from app.defaults import DEFAULTS

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10


def load_smtp_settings(db) -> dict | None:
    """读 settings 拼 SMTP 配置；host/user/to 任一缺失视为未配置，返回 None。

    畸形值（端口非数字、to 非列表）一律按未配置处理——绝不抛异常：
    send_mail 的三态契约是调用方（fire-and-forget 告警路径）静默安全的前提。
    """
    host = models.get_setting(db, "smtp_host", DEFAULTS["smtp_host"])
    user = models.get_setting(db, "smtp_user", DEFAULTS["smtp_user"])
    to = models.get_setting(db, "smtp_to", DEFAULTS["smtp_to"])
    if not isinstance(to, list):
        return None
    recipients = [t for t in to if isinstance(t, str) and t.strip()]
    if not host or not user or not recipients:
        return None
    try:
        port = int(models.get_setting(db, "smtp_port", DEFAULTS["smtp_port"]))
    except (TypeError, ValueError):
        return None
    if not 1 <= port <= 65535:
        return None
    return {
        "host": host,
        "port": port,
        "user": user,
        "pass": models.get_setting(db, "smtp_pass", ""),
        "from": models.get_setting(db, "smtp_from", DEFAULTS["smtp_from"]) or user,
        "to": recipients,
    }


def smtp_configured(db) -> bool:
    return load_smtp_settings(db) is not None


def send_sync(settings: dict, subject: str, body: str) -> None:
    """同步发信（线程池里跑）。抛异常即失败，重试/告警由调用方决定。"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings["from"]
    msg["To"] = ", ".join(settings["to"])
    msg["Date"] = formatdate()  # 缺 Date/Message-ID 易被判垃圾邮件
    port = settings["port"]
    if port == 465:
        smtp = smtplib.SMTP_SSL(settings["host"], port, timeout=SMTP_TIMEOUT_SECONDS)
    else:
        smtp = smtplib.SMTP(settings["host"], port, timeout=SMTP_TIMEOUT_SECONDS)
    try:
        smtp.ehlo()
        if port != 465 and smtp.has_extn("starttls"):
            smtp.starttls()
            smtp.ehlo()
        if settings["pass"]:
            smtp.login(settings["user"], settings["pass"])
        smtp.sendmail(settings["from"], settings["to"], msg.as_string())
    finally:
        smtp.quit()


async def send_mail(db, subject: str, body: str) -> bool | None:
    """三态：None=未配置（静默跳过）；True=已发出；False=重试 1 次后仍失败。"""
    settings = load_smtp_settings(db)
    if settings is None:
        return None
    for attempt in (1, 2):
        try:
            await asyncio.to_thread(send_sync, settings, subject, body)
            return True
        except Exception:
            if attempt == 2:
                logger.exception("邮件发送失败（已重试一次）")
                return False
    return False
