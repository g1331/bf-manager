"""公共查询限流：按 IP（IPv6 按 /64）或登录账号，在 Redis 里做固定窗口计数。

用法是在路由上挂 ``dependencies=[rate_limit("lookup")]``。依赖同时把请求标记为公共查询，
让后续的 EA 调用计入全站预算（见 ``app.core.ea_budget``）。

- 登录用户按账号计数，额度乘以 ``rate_limit_user_multiplier``；同一出口 IP 后面的多人
  （学校、网吧、运营商 NAT）登录后互不影响。
- 内网和本机地址不限流、也不计入 EA 预算：生产上真实客户端 IP 由 openresty 还原，
  只有本机运维脚本、Next 服务端这类内部请求才会是私有地址。
- Redis 不可用时放行，限流本身不能成为查询的单点故障。
"""

from __future__ import annotations

import ipaddress
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, Request
from loguru import logger

from app.api.client_ip import client_ip
from app.api.errors import TooManyRequestsError
from app.core import ea_budget
from app.core.cache import get_redis
from app.core.config import Settings, get_settings
from app.services.metrics_service import user_id_from_token

SESSION_COOKIE = "bfm_access_token"

# 桶名 → [(窗口秒数, 读取额度的配置项)]
_BUCKETS: dict[str, list[tuple[int, str]]] = {
    "lookup": [(60, "rate_limit_lookup_per_minute"), (86400, "rate_limit_lookup_per_day")],
    "avatar": [(60, "rate_limit_avatar_per_minute")],
    "ea_login": [(600, "rate_limit_ea_login_per_10min")],
}

# 被拦次数按天累计，留 8 天，上线后据此调整额度
_BLOCKED_TTL_SECONDS = 8 * 86400


def _ip_subject(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return f"ip:{ip}"
    if addr.is_private or addr.is_loopback:
        return None
    if addr.version == 6:
        # 一个 IPv6 用户通常独占一个 /64，按单个地址计数等于不限
        return f"ip6:{ipaddress.ip_network(f'{addr}/64', strict=False).network_address}"
    return f"ip:{addr}"


def _subject(request: Request, settings: Settings) -> tuple[str, int] | None:
    """返回 (计数主体, 额度倍数)；不需要限流时返回 None。"""
    user_id = user_id_from_token(request.cookies.get(SESSION_COOKIE))
    if user_id is not None:
        return f"user:{user_id}", max(settings.rate_limit_user_multiplier, 1)
    ip_key = _ip_subject(client_ip(request))
    return (ip_key, 1) if ip_key else None


def _wait_text(seconds: int) -> str:
    if seconds >= 3600:
        return f"{(seconds + 3599) // 3600} 小时"
    if seconds >= 60:
        return f"{(seconds + 59) // 60} 分钟"
    return f"{seconds} 秒"


async def _record_blocked(bucket: str) -> None:
    try:
        r = await get_redis()
        key = f"bfm:rl:blocked:{datetime.now(UTC):%Y%m%d}:{bucket}"
        await r.incr(key)
        await r.expire(key, _BLOCKED_TTL_SECONDS)
    except Exception as e:
        logger.debug("限流拦截计数失败: {!r}", e)


def rate_limit(bucket: str) -> Any:
    """返回可放进路由 ``dependencies=[...]`` 的依赖。"""
    rules = _BUCKETS[bucket]

    async def _check(request: Request) -> None:
        settings = get_settings()
        subject = _subject(request, settings)
        if subject is None:
            # 内网、本机的请求既不限流也不计入公共 EA 预算
            return
        ea_budget.mark_public()
        if not settings.rate_limit_enabled:
            return
        name, multiplier = subject

        now = int(time.time())
        windows: list[tuple[int, int, int]] = []  # (窗口起点, 窗口长度, 额度)
        try:
            r = await get_redis()
            async with r.pipeline(transaction=False) as pipe:
                for window, limit_attr in rules:
                    start = now - now % window
                    key = f"bfm:rl:{bucket}:{window}:{name}:{start}"
                    pipe.incr(key)
                    pipe.expire(key, window + 5)
                    windows.append((start, window, getattr(settings, limit_attr) * multiplier))
                results = await pipe.execute()
        except Exception as e:
            logger.warning("限流计数失败，放行: {!r}", e)
            return

        for (start, window, limit), count in zip(windows, results[0::2], strict=True):
            if int(count) > limit:
                await _record_blocked(bucket)
                retry_after = start + window - now
                raise TooManyRequestsError(
                    f"本站为公益项目，查询账号有限，请 {_wait_text(retry_after)}后再试",
                    retry_after=retry_after,
                )

    return Depends(_check)
