"""BF6 玩家查询：名字 → nucleus，nucleus → 生涯战绩。

缓存（Redis 不可用时直接查上游）：
- 当前赛季 event id 1 小时；
- 名字解析 1 小时，查无此人 10 分钟；
- 归一化后的战绩 20 分钟。原始响应可达 1.5 MB，不缓存也不下发。

每次向 EA 读到生涯都交给 ``match_service`` 存快照、算对局估算；后台复查也走这里的 ``fetch_batch``。

同一玩家的并发请求在进程内合并成一次上游调用；真正打到 EA 的那次计入公共查询预算。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.api.errors import EAApiError, EARejectedError
from app.core import ea_budget
from app.core.cache import get_cache
from app.domain.games.bf6 import client as bf6
from app.domain.games.bf6 import resolver
from app.domain.games.bf6.wire import PlayerStats
from app.schemas.bf6.player import Bf6PlayerStats, Bf6ResolvedPlayer
from app.services.account_service import SessionFactory
from app.services.bf6 import credential_service, match_service
from app.services.bf6.stats_normalizer import global_stats, normalize_global

_EVENT_KEY = "bf6:event"
_EVENT_TTL = 3600
_RESOLVE_TTL = 3600
_RESOLVE_MISS_TTL = 600
_STATS_TTL = 1200
# 返回结构变了就换版本号，旧结构的缓存不再读
_STATS_KEY = "bf6:stats:v2:{}"

_inflight: dict[int, asyncio.Task[Bf6PlayerStats]] = {}


async def _cache_get(key: str) -> Any:
    try:
        return await (await get_cache()).get(key)
    except (RedisError, OSError) as e:
        logger.warning("BF6 缓存读取失败 {}: {!r}", key, e)
        return None


async def _cache_set(key: str, value: Any, ttl: int) -> None:
    try:
        await (await get_cache()).set(key, value, ttl=ttl)
    except (RedisError, OSError) as e:
        logger.warning("BF6 缓存写入失败 {}: {!r}", key, e)


def _upstream_error(e: bf6.Bf6Error) -> EAApiError:
    if isinstance(e, bf6.Bf6CredentialError):
        return EAApiError("BF6_UNAVAILABLE", "BF6 查询暂不可用，请稍后再试")
    return EAApiError(
        "BF6_UPSTREAM_ERROR", "EA 暂时没有正常响应，请稍后再试", retryable=e.retryable
    )


async def _current_event(http: httpx.AsyncClient, *, refresh: bool = False) -> str:
    if not refresh:
        cached = await _cache_get(_EVENT_KEY)
        if isinstance(cached, str) and cached:
            return cached
    await ea_budget.acquire()
    event_id = await resolver.fetch_current_event(http)
    await _cache_set(_EVENT_KEY, event_id, _EVENT_TTL)
    return event_id


async def resolve_player(name: str, platform: resolver.Bf6Platform | None) -> Bf6ResolvedPlayer:
    """按 EA 显示名找玩家；找不到抛 422 BF6_PLAYER_NOT_FOUND。"""
    query = resolver.normalize_name(name)
    # EA 显示名不区分大小写（jackfrags 搜得到 JackFrags）
    key = f"bf6:resolve:{platform or 'any'}:{query.casefold()}"
    cached = await _cache_get(key)
    if isinstance(cached, dict):
        if cached.get("missing"):
            raise _not_found(query)
        return Bf6ResolvedPlayer(**cached)

    try:
        async with httpx.AsyncClient(timeout=20) as http:
            event_id = await _current_event(http)
            await ea_budget.acquire()
            found = await resolver.lookup(http, query, event_id, platform)
            if found is None:
                # 换季后缓存里的 event id 可能已失效，拿最新的再确认一次
                latest = await _current_event(http, refresh=True)
                if latest != event_id:
                    await ea_budget.acquire()
                    found = await resolver.lookup(http, query, latest, platform)
    except bf6.Bf6Error as e:
        raise _upstream_error(e) from e

    if found is None:
        await _cache_set(key, {"missing": True}, _RESOLVE_MISS_TTL)
        raise _not_found(query)
    result = Bf6ResolvedPlayer(
        nucleus_id=found.nucleus_id,
        display_name=found.display_name,
        platform=found.platform,
        avatar_url=found.avatar_url,
        has_current_season_stats=found.has_current_season_stats,
    )
    await _cache_set(key, result.model_dump(), _RESOLVE_TTL)
    return result


def _not_found(query: str) -> EARejectedError:
    return EARejectedError(
        "BF6_PLAYER_NOT_FOUND",
        f"没有找到 EA 显示名为「{query}」的玩家。Steam 玩家请用 EA 账号的显示名搜索",
    )


async def _get_stats(session_factory: SessionFactory, nucleus_ids: list[int]) -> list[PlayerStats]:
    """会话被网关拒绝时换一个新会话重试一次。"""
    try:
        token = await credential_service.get_session_jwt(session_factory)
        return await bf6.get_stats(token, nucleus_ids)
    except bf6.Bf6SessionExpiredError:
        token = await credential_service.get_session_jwt(session_factory, renew=True)
        return await bf6.get_stats(token, nucleus_ids)


async def _fetch_stats(session_factory: SessionFactory, nucleus_id: int) -> Bf6PlayerStats:
    await ea_budget.acquire()
    try:
        players = await _get_stats(session_factory, [nucleus_id])
    except bf6.Bf6Error as e:
        logger.warning("BF6 getStats 失败 nucleus={}: {}", nucleus_id, e)
        raise _upstream_error(e) from e
    player = next((p for p in players if p.player.nucleus_id == nucleus_id), None)
    if player is None and len(players) == 1:
        player = players[0]
    now = datetime.now(UTC)
    stats = global_stats(player)
    try:
        await match_service.record(session_factory, nucleus_id, stats, now, viewed=True)
    except SQLAlchemyError as e:
        # 对局估算是附带的，写不进去不影响查战绩
        logger.warning("BF6 快照写库失败 nucleus={}: {!r}", nucleus_id, e)
    return normalize_global(stats, nucleus_id, now)


async def _fetch_and_cache(session_factory: SessionFactory, nucleus_id: int) -> Bf6PlayerStats:
    started = time.monotonic()
    result = await _fetch_stats(session_factory, nucleus_id)
    logger.info("BF6 战绩 nucleus={} 用时 {:.1f}s", nucleus_id, time.monotonic() - started)
    await _cache_stats(result)
    return result


async def _cache_stats(result: Bf6PlayerStats) -> None:
    await _cache_set(
        _STATS_KEY.format(result.nucleus_id), result.model_dump(mode="json"), _STATS_TTL
    )


async def fetch_batch(
    session_factory: SessionFactory, nucleus_ids: list[int]
) -> dict[int, dict[str, int]]:
    """后台复查用：一次读一批人的生涯，顺带刷新他们的战绩缓存。不计入公共查询预算。"""
    players = await _get_stats(session_factory, nucleus_ids)
    now = datetime.now(UTC)
    wanted = set(nucleus_ids)
    out: dict[int, dict[str, int]] = {}
    for player in players:
        nucleus_id = player.player.nucleus_id
        stats = global_stats(player)
        if nucleus_id not in wanted or not stats:
            continue
        out[nucleus_id] = stats
        await _cache_stats(normalize_global(stats, nucleus_id, now))
    return out


def _settle(nucleus_id: int, task: asyncio.Task[Bf6PlayerStats]) -> None:
    _inflight.pop(nucleus_id, None)
    # 所有等待者都断开时也要取走异常，免得打印 “Task exception was never retrieved”
    if not task.cancelled():
        task.exception()


async def get_player_stats(session_factory: SessionFactory, nucleus_id: int) -> Bf6PlayerStats:
    cached = await _cache_get(_STATS_KEY.format(nucleus_id))
    if isinstance(cached, dict):
        try:
            await match_service.touch(session_factory, nucleus_id, datetime.now(UTC))
        except SQLAlchemyError as e:
            logger.warning("BF6 记录查看时间失败 nucleus={}: {!r}", nucleus_id, e)
        return Bf6PlayerStats(**cached)

    # 上游调用放进独立任务：发起请求的客户端断开也不会取消它，其余等待者照样拿到结果
    task = _inflight.get(nucleus_id)
    if task is None:
        task = asyncio.create_task(_fetch_and_cache(session_factory, nucleus_id))
        _inflight[nucleus_id] = task
        task.add_done_callback(lambda t: _settle(nucleus_id, t))
    return await asyncio.shield(task)
