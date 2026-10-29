"""公共查询的 EA 预算：全站每分钟最多让匿名或普通查询占用多少次 EA 账号池 / Blaze 连接。

按 IP 限流挡不住很多 IP 一起来的情况，这里再加一道全局闸门。只有经过
``rate_limit`` 依赖的公共查询路由会被标记为 ``public``；管服操作、后台轮询和对局跟踪
保持默认的 ``system``，不计入预算，所以有人刷战绩接口时服主照样能踢人、封禁。

缓存命中走不到账号池和 Blaze，自然不占预算。Redis 不可用时放行。
"""

from __future__ import annotations

import time
from contextvars import ContextVar

from loguru import logger

from app.api.errors import EABusyError
from app.core.cache import get_redis
from app.core.config import get_settings

_priority: ContextVar[str] = ContextVar("ea_priority", default="system")


def mark_public() -> None:
    """把当前请求标记为公共查询；之后同一请求里（含它创建的子任务）的 EA 调用计入预算。"""
    _priority.set("public")


def is_public() -> bool:
    return _priority.get() == "public"


async def acquire() -> None:
    """公共查询每占用一次账号池或 Blaze 连接前调用；本分钟超出预算时抛 EABusyError。"""
    if not is_public():
        return
    budget = get_settings().ea_public_budget_per_minute
    if budget <= 0:
        return
    now = int(time.time())
    window_start = now - now % 60
    key = f"bfm:ea_budget:public:{window_start}"
    try:
        r = await get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 120)
    except Exception as e:
        logger.warning("EA 预算计数失败，放行: {!r}", e)
        return
    if count > budget:
        if count == budget + 1:
            logger.warning("公共查询 EA 预算本分钟已用完（{} 次）", budget)
        raise EABusyError(retry_after=window_start + 60 - now)
