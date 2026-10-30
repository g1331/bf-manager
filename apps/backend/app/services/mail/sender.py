"""发信通道：生产走 Resend HTTP API，开发和测试只写日志。

走 HTTP API 而不是 SMTP：2026-10-30 实测两种通道的邮件头里都没有源站 IP，API 报错更好读，
也不用维护 SMTP 连接。发信失败只记日志、不抛出，调用方都在后台任务里，用户可以点“重发”。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
from loguru import logger

from app.core.config import get_settings

RESEND_ENDPOINT = "https://api.resend.com/emails"


@dataclass(frozen=True)
class MailMessage:
    to: str
    subject: str
    text: str
    html: str
    # 写进日志、方便排查是哪类信，不进邮件
    kind: str = ""


class MailSender(Protocol):
    async def send(self, message: MailMessage) -> bool: ...


class LogMailSender:
    """只写日志。outbox 留着最近发出的信，测试从这里取链接。"""

    def __init__(self) -> None:
        self.outbox: list[MailMessage] = []

    async def send(self, message: MailMessage) -> bool:
        self.outbox.append(message)
        del self.outbox[:-50]
        logger.info("mail(log) kind={} subject={}\n{}", message.kind, message.subject, message.text)
        return True


class ResendMailSender:
    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    async def send(self, message: MailMessage) -> bool:
        payload = {
            "from": self._sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
            "html": message.html,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    RESEND_ENDPOINT,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except Exception as e:
            logger.warning("mail send failed kind={}: {!r}", message.kind, e)
            return False
        if resp.status_code >= 400:
            # 响应里只有错误说明，不含收件人以外的敏感信息
            logger.warning(
                "mail send rejected kind={} status={} body={}",
                message.kind,
                resp.status_code,
                resp.text[:300],
            )
            return False
        logger.info("mail sent kind={} id={}", message.kind, resp.json().get("id"))
        return True


_sender: MailSender | None = None


def get_mail_sender() -> MailSender:
    global _sender  # noqa: PLW0603
    if _sender is None:
        settings = get_settings()
        if settings.mail_backend == "resend":
            if not settings.resend_api_key:
                raise RuntimeError("MAIL_BACKEND=resend 但没有配置 resend_api_key")
            _sender = ResendMailSender(settings.resend_api_key, settings.mail_from)
        else:
            _sender = LogMailSender()
    return _sender


def set_mail_sender(sender: MailSender | None) -> None:
    """测试用：换成自己的 sender；传 None 恢复按配置创建。"""
    global _sender  # noqa: PLW0603
    _sender = sender
