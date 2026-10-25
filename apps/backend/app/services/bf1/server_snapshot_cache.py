"""BF1 全服服务器摘要缓存

全服统计轮询每轮把去重后的服务器摘要整体写入 Redis，服务器搜索与概览页「热门服务器」
直接读这份缓存，不再各自请求 EA。只存 ServerSummary 字段，快照原始项里的 HNET 等隐私
字段不会进缓存。单独成模块是为了让 overview_service 与 server_service 都能引用而不循环导入。
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from redis.exceptions import RedisError

from app.core.cache import get_cache
from app.schemas.bf1.server import ServerSummary

SERVER_SNAPSHOT_CACHE_KEY = "bf1:servers:snapshot"


async def write_server_snapshot(summaries: list[ServerSummary], *, source: str, ttl: int) -> None:
    cache = await get_cache()
    await cache.set(
        SERVER_SNAPSHOT_CACHE_KEY,
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "source": source,
            "items": [s.model_dump() for s in summaries],
        },
        ttl=ttl,
    )


async def read_server_snapshot() -> list[ServerSummary] | None:
    """读最近一轮的全服服务器摘要。缓存缺失、过期或 Redis 不可用时返回 None。

    source=snapshot 时只含有人的服（快照 PMIN 1）；source=search 时是 searchServers 去重结果。
    """
    try:
        cache = await get_cache()
        cached = await cache.get(SERVER_SNAPSHOT_CACHE_KEY)
    except RedisError as e:
        logger.warning("BF1 server snapshot cache read failed: {}", e)
        return None
    if not isinstance(cached, dict):
        return None
    return [ServerSummary(**item) for item in cached.get("items") or []]
