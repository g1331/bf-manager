"""Redis 缓存封装"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
from loguru import logger

from app.core.config import get_settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis  # noqa: PLW0603
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
        logger.info("Redis connection initialized: {}", settings.redis_url)
    return _redis


async def close_redis() -> None:
    global _redis  # noqa: PLW0603
    if _redis is not None:
        await _redis.close()
        _redis = None


class Cache:
    """简易 JSON 序列化缓存"""

    def __init__(self, client: aioredis.Redis, prefix: str = "bfm") -> None:
        self._r = client
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str) -> Any | None:
        raw = await self._r.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        data = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        await self._r.set(self._key(key), data, ex=ttl)

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        full = [self._key(k) for k in keys]
        return await self._r.delete(*full)

    async def exists(self, key: str) -> bool:
        return bool(await self._r.exists(self._key(key)))


async def get_cache() -> Cache:
    return Cache(await get_redis())
