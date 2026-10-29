"""本地账号登录防爆破：按用户名与 IP 统计 15 分钟内的失败次数，超限后锁到窗口结束。

计数放在 Redis；Redis 不可用时放行，不让限流本身成为登录的单点故障。
"""

from __future__ import annotations

from loguru import logger

from app.api.errors import TooManyRequestsError
from app.core.cache import get_redis

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_USER = 5
MAX_FAILURES_PER_IP = 20

_PREFIX = "bfm:login_fail"


def _user_key(username: str) -> str:
    return f"{_PREFIX}:user:{username.strip().lower()}"


def _ip_key(ip: str) -> str:
    return f"{_PREFIX}:ip:{ip}"


def _limits(username: str, ip: str | None) -> list[tuple[str, int]]:
    limits = [(_user_key(username), MAX_FAILURES_PER_USER)]
    if ip:
        limits.append((_ip_key(ip), MAX_FAILURES_PER_IP))
    return limits


async def ensure_not_locked(username: str, ip: str | None) -> None:
    """失败次数已达上限时抛 429，提示剩余等待时间。"""
    try:
        r = await get_redis()
        for key, limit in _limits(username, ip):
            count = await r.get(key)
            if count is not None and int(count) >= limit:
                ttl = await r.ttl(key)
                wait = ttl if ttl > 0 else WINDOW_SECONDS
                minutes = max((wait + 59) // 60, 1)
                raise TooManyRequestsError(
                    f"登录失败次数过多，请 {minutes} 分钟后再试", retry_after=wait
                )
    except TooManyRequestsError:
        raise
    except Exception as e:
        logger.warning("登录限流检查失败，放行: {!r}", e)


async def record_failure(username: str, ip: str | None) -> None:
    try:
        r = await get_redis()
        for key, _ in _limits(username, ip):
            # 窗口从第一次失败开始计时，后续失败不续期，锁定时长有上限
            if await r.incr(key) == 1:
                await r.expire(key, WINDOW_SECONDS)
    except Exception as e:
        logger.warning("登录失败计数写入失败: {!r}", e)


async def clear(username: str) -> None:
    """登录成功后清零该用户名的计数；IP 计数保留，防止用一个已知账号洗掉 IP 上的失败记录。"""
    try:
        r = await get_redis()
        await r.delete(_user_key(username))
    except Exception as e:
        logger.warning("登录失败计数清理失败: {!r}", e)
