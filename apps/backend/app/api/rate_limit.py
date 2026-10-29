"""公共查询限流：按 API Key、登录账号或 IP（IPv6 按 /64），在 Redis 里做固定窗口计数。

用法是在路由上挂 ``dependencies=[rate_limit("lookup")]``。依赖同时把请求标记为公共查询，
让后续的 EA 调用计入全站预算（见 ``app.core.ea_budget``）。

- 带 ``X-API-Key`` 的请求按 key 计数，额度乘以该 key 的倍数，只在公开查询的桶里认；
  key 无效直接 401，免得调用方以为在用 key、其实按 IP 被限。
- 登录用户按账号计数，额度乘以 ``rate_limit_user_multiplier``；同一出口 IP 后面的多人
  （学校、网吧、运营商 NAT）登录后互不影响。
- 内网和本机地址不限流、也不计入 EA 预算：生产上真实客户端 IP 由 openresty 还原，
  只有本机运维脚本、Next 服务端这类内部请求才会是私有地址。
- Redis 不可用时放行，限流本身不能成为查询的单点故障。
- 响应带 ``RateLimit-Limit`` / ``RateLimit-Remaining`` / ``RateLimit-Reset``，取剩余最少的窗口，
  调用方据此控制节奏。
"""

from __future__ import annotations

import ipaddress
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, Request, Response
from loguru import logger

from app.api.client_ip import client_ip
from app.api.deps import DbDep
from app.api.errors import TooManyRequestsError, UnauthorizedError
from app.core import ea_budget
from app.core.cache import get_redis
from app.core.config import Settings, get_settings
from app.services import api_key_service
from app.services.metrics_service import user_id_from_token

SESSION_COOKIE = "bfm_access_token"
API_KEY_HEADER = "X-API-Key"

# 桶名 → [(窗口秒数, 读取额度的配置项)]
_BUCKETS: dict[str, list[tuple[int, str]]] = {
    "lookup": [(60, "rate_limit_lookup_per_minute"), (86400, "rate_limit_lookup_per_day")],
    "avatar": [(60, "rate_limit_avatar_per_minute")],
    "read": [(60, "rate_limit_read_per_minute"), (86400, "rate_limit_read_per_day")],
    "ea_login": [(600, "rate_limit_ea_login_per_10min")],
    "card_check": [(3600, "rate_limit_card_check_per_hour")],
    "card_start": [(3600, "rate_limit_card_start_per_hour")],
}

# API Key 只用于公开查询；登录、卡行动这类桶照旧按账号或 IP 计
_KEY_BUCKETS = {"lookup", "read", "avatar"}

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


async def _subject(
    request: Request, settings: Settings, db: DbDep, bucket: str
) -> tuple[str, int, int | None] | None:
    """返回 (计数主体, 额度倍数, API Key id)；不需要限流时返回 None。"""
    raw_key = request.headers.get(API_KEY_HEADER) if bucket in _KEY_BUCKETS else None
    if raw_key:
        key = await api_key_service.resolve(db, raw_key.strip())
        if key is None:
            raise UnauthorizedError("API Key 无效或已吊销")
        await api_key_service.touch(db, key.id)
        return f"key:{key.id}", key.multiplier, key.id
    user_id = user_id_from_token(request.cookies.get(SESSION_COOKIE))
    if user_id is not None:
        return f"user:{user_id}", max(settings.rate_limit_user_multiplier, 1), None
    ip_key = _ip_subject(client_ip(request))
    return (ip_key, 1, None) if ip_key else None


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

    async def _check(request: Request, response: Response, db: DbDep) -> None:
        settings = get_settings()
        subject = await _subject(request, settings, db, bucket)
        if subject is None:
            # 内网、本机的请求既不限流也不计入公共 EA 预算
            return
        ea_budget.mark_public()
        if not settings.rate_limit_enabled:
            return
        name, multiplier, key_id = subject

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
                if key_id is not None:
                    usage = api_key_service.usage_key(key_id, datetime.now(UTC))
                    pipe.incr(usage)
                    pipe.expire(usage, api_key_service.USAGE_TTL_SECONDS)
                results = await pipe.execute()
        except Exception as e:
            logger.warning("限流计数失败，放行: {!r}", e)
            return

        counts = results[0::2][: len(windows)]
        # 头部报剩余最少的那个窗口
        start, window, limit, count = min(
            ((st, w, lim, int(c)) for (st, w, lim), c in zip(windows, counts, strict=True)),
            key=lambda x: x[2] - x[3],
        )
        response.headers["RateLimit-Limit"] = str(limit)
        response.headers["RateLimit-Remaining"] = str(max(limit - count, 0))
        response.headers["RateLimit-Reset"] = str(start + window - now)

        for (start, window, limit), count in zip(windows, counts, strict=True):
            if int(count) > limit:
                await _record_blocked(bucket)
                retry_after = start + window - now
                raise TooManyRequestsError(
                    f"本站为公益项目，查询账号有限，请 {_wait_text(retry_after)}后再试",
                    retry_after=retry_after,
                )

    return Depends(_check)
