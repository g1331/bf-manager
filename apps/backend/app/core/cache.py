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
        await _redis.aclose()
        _redis = None


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


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

    async def hash_set(self, key: str, field: str, value: str, *, ttl: int | None = None) -> None:
        """写入 hash 的一个字段；ttl 作用于整个 key，每次写入都续期。"""
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.hset(self._key(key), field, value)
            if ttl is not None:
                pipe.expire(self._key(key), ttl)
            await pipe.execute()

    async def hash_all(self, key: str) -> dict[str, str]:
        raw = await self._r.hgetall(self._key(key))
        # 连接开了 decode_responses，这里只是把类型收窄到 str
        return {_text(k): _text(v) for k, v in raw.items()}

    async def hash_delete(self, key: str, *fields: str) -> int:
        if not fields:
            return 0
        return await self._r.hdel(self._key(key), *fields)

    async def list_append(
        self, key: str, value: Any, *, max_len: int, ttl: int | None = None
    ) -> None:
        """向列表尾部追加一个 JSON 元素并裁剪到最近 max_len 条，用于固定长度的时间序列。"""
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.rpush(self._key(key), json.dumps(value, ensure_ascii=False))
            pipe.ltrim(self._key(key), -max_len, -1)
            if ttl is not None:
                pipe.expire(self._key(key), ttl)
            await pipe.execute()

    async def list_all(self, key: str) -> list[Any]:
        """读取整个列表并逐条 JSON 反序列化，无法解析的脏元素直接跳过。"""
        raw = await self._r.lrange(self._key(key), 0, -1)
        items: list[Any] = []
        for entry in raw:
            try:
                items.append(json.loads(entry))
            except json.JSONDecodeError:
                continue
        return items


async def get_cache() -> Cache:
    return Cache(await get_redis())
