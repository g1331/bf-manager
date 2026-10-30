"""Cloudflare Turnstile 人机验证：挂在会触发发信的接口上（注册、找回密码、补邮箱）。

Resend 免费档一天只能发 100 封，靠 IP 限流挡不住换 IP 刷信。前端把 Turnstile 给的 token
放在 ``X-Turnstile-Token`` 请求头里，这里拿去 Cloudflare 校验。

- secret 和 site key 没配齐时直接放行（开发、测试环境）；前端也只在配齐时显示验证框。
- 我们这边调 Cloudflare 出错时放行并记日志：攻击者没法让我们的出站请求失败，
  不因为 Cloudflare 偶发故障把所有人挡在门外。
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends, Request
from loguru import logger

from app.api.client_ip import client_ip
from app.api.errors import AppError
from app.core.config import get_settings

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_HEADER = "X-Turnstile-Token"


class CaptchaError(AppError):
    def __init__(self) -> None:
        super().__init__(400, "CAPTCHA_FAILED", "人机验证没有通过，请刷新页面重试")


async def _verify(token: str, ip: str | None) -> bool | None:
    """True 通过，False 不通过，None 校验服务出错"""
    data = {"secret": get_settings().turnstile_secret_key, "response": token}
    if ip:
        data["remoteip"] = ip
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(SITEVERIFY_URL, data=data)
        body = resp.json()
    except Exception as e:
        logger.warning("Turnstile 校验请求失败，放行: {!r}", e)
        return None
    if not body.get("success"):
        logger.info("Turnstile 未通过: {}", body.get("error-codes"))
        return False
    return True


def turnstile_enabled() -> bool:
    settings = get_settings()
    return bool(settings.turnstile_secret_key and settings.turnstile_site_key)


def require_turnstile() -> Any:
    async def _check(request: Request) -> None:
        if not turnstile_enabled():
            return
        token = (request.headers.get(TOKEN_HEADER) or "").strip()
        if not token or len(token) > 2048:
            raise CaptchaError()
        if await _verify(token, client_ip(request)) is False:
            raise CaptchaError()

    return Depends(_check)
