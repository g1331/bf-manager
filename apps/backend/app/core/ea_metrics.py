"""EA 调用计数

每次向 EA 发请求（Blaze ``socket.send``、Gateway JSON-RPC 与几个登录用的 HTTP 请求）都调
:func:`count` 记一笔，按「通道 | 方法 | 来源」累加在进程内，后台每 30 秒合并写入 Redis。
来源用 contextvar 标记：API 请求由中间件按接口分组设成 ``api:bf1/stats`` 这类值，后台任务
各自用 :func:`ea_source` 设成 ``tracker``、``snapshot`` 等；子任务创建时继承当时的来源。

Redis 键（都挂在 ``bfm:metrics:ea`` 下）：
- ``day:{YYYYMMDD}`` / ``hour:{YYYYMMDDHH}`` 哈希，字段 ``通道|方法|来源`` → 次数
- ``pids:day:{YYYYMMDD}`` 哈希，字段为来源 → ``Stats.getStats`` 查询的人次，用来算批次填充率
- ``tracker:day:{YYYYMMDD}`` 哈希，对局跟踪器的事件计数（按原因查了多少人、进服的人是不是换服来的、
  复查有没有查出变化），用来判断哪些查询可以省

计数只是运维观察用，写入失败就丢掉这一批，不影响业务。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import Counter
from collections.abc import Iterator
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from app.core.cache import get_redis

PREFIX = "bfm:metrics:ea"
DAY_TTL_SECONDS = 60 * 60 * 24 * 40
HOUR_TTL_SECONDS = 60 * 60 * 24 * 3
FLUSH_SECONDS = 30

_source: ContextVar[str] = ContextVar("ea_source", default="other")
_calls: Counter[str] = Counter()
_pids: Counter[str] = Counter()
_events: Counter[str] = Counter()


def set_source(source: str) -> None:
    """把当前上下文（及之后创建的子任务）的来源设为 source。"""
    _source.set(source)


@contextlib.contextmanager
def ea_source(source: str) -> Iterator[None]:
    token = _source.set(source)
    try:
        yield
    finally:
        _source.reset(token)


def count(channel: str, method: str) -> None:
    _calls[f"{channel}|{method}|{_source.get()}"] += 1


def count_pids(n: int) -> None:
    _pids[_source.get()] += n


def count_event(name: str, n: int = 1) -> None:
    if n:
        _events[name] += n


def _take() -> tuple[Counter[str], Counter[str], Counter[str]]:
    calls, pids, events = _calls.copy(), _pids.copy(), _events.copy()
    _calls.clear()
    _pids.clear()
    _events.clear()
    return calls, pids, events


async def flush(redis: Any, now: datetime | None = None) -> None:
    """把进程内累计的次数写进 Redis。失败时这一批作废，只记 debug 日志。"""
    calls, pids, events = _take()
    if not calls and not pids and not events:
        return
    now = now or datetime.now(UTC)
    day_key = f"{PREFIX}:day:{now:%Y%m%d}"
    hour_key = f"{PREFIX}:hour:{now:%Y%m%d%H}"
    pids_key = f"{PREFIX}:pids:day:{now:%Y%m%d}"
    events_key = f"{PREFIX}:tracker:day:{now:%Y%m%d}"
    try:
        pipe = redis.pipeline()
        for field, n in calls.items():
            pipe.hincrby(day_key, field, n)
            pipe.hincrby(hour_key, field, n)
        for field, n in pids.items():
            pipe.hincrby(pids_key, field, n)
        for field, n in events.items():
            pipe.hincrby(events_key, field, n)
        pipe.expire(day_key, DAY_TTL_SECONDS)
        pipe.expire(hour_key, HOUR_TTL_SECONDS)
        pipe.expire(pids_key, DAY_TTL_SECONDS)
        pipe.expire(events_key, DAY_TTL_SECONDS)
        await pipe.execute()
    except Exception as e:
        logger.debug("EA metrics flush skipped: {}", e)


async def ea_metrics_flusher() -> None:
    """后台循环：定时写入；停机取消时把最后一批也写掉。"""
    try:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            with contextlib.suppress(Exception):
                await flush(await get_redis())
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await flush(await get_redis())
        raise
