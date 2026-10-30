"""开放 API Key：签发、吊销、校验与用量统计。

key 形如 ``bfm_`` 加 43 位随机串，库里只存 sha256（key 本身是高熵随机串，不需要慢哈希）。
校验结果在 Redis 里缓存 60 秒，吊销时同时删缓存，不用每个请求都查库。
用量按天计在 Redis，留 8 天；``last_used_at`` 最多每 5 分钟写一次库。
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError, ValidationError
from app.core.cache import get_redis
from app.core.config import get_settings
from app.models import ApiKey, User

KEY_PREFIX = "bfm_"
_CACHE_TTL_SECONDS = 60
USAGE_TTL_SECONDS = 8 * 86400
_TOUCH_INTERVAL_SECONDS = 300
_INVALID = "-"


@dataclass(frozen=True)
class ResolvedKey:
    id: int
    multiplier: int


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_key(key_hash: str) -> str:
    return f"bfm:apikey:{key_hash}"


def usage_key(key_id: int, day: datetime) -> str:
    return f"bfm:apikey:use:{key_id}:{day:%Y%m%d}"


def effective_multiplier(key: ApiKey) -> int:
    return max(key.rate_multiplier or get_settings().rate_limit_api_key_multiplier, 1)


async def resolve(db: AsyncSession, raw: str) -> ResolvedKey | None:
    """校验请求带来的 key；无效、已吊销或所属用户被停用时返回 None。"""
    if not raw.startswith(KEY_PREFIX) or len(raw) > 128:
        return None
    key_hash = hash_key(raw)
    try:
        r = await get_redis()
        cached = await r.get(_cache_key(key_hash))
    except Exception as e:
        logger.debug("API Key 缓存读取失败，改查库: {!r}", e)
        r, cached = None, None
    if cached is not None:
        if cached == _INVALID:
            return None
        key_id, multiplier = cached.split(":")
        return ResolvedKey(int(key_id), int(multiplier))

    row = await db.scalar(
        select(ApiKey)
        .join(User, User.id == ApiKey.user_id)
        .where(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked_at.is_(None),
            User.is_active.is_(True),
            User.is_frozen.is_(False),
        )
    )
    resolved = ResolvedKey(row.id, effective_multiplier(row)) if row else None
    if r is not None:
        value = f"{resolved.id}:{resolved.multiplier}" if resolved else _INVALID
        try:
            await r.set(_cache_key(key_hash), value, ex=_CACHE_TTL_SECONDS)
        except Exception as e:
            logger.debug("API Key 缓存写入失败: {!r}", e)
    return resolved


async def touch(db: AsyncSession, key_id: int) -> None:
    """最多每 5 分钟把 last_used_at 写回库一次。"""
    try:
        r = await get_redis()
        if not await r.set(f"bfm:apikey:seen:{key_id}", 1, ex=_TOUCH_INTERVAL_SECONDS, nx=True):
            return
    except Exception:
        return
    await db.execute(update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=func.now()))
    await db.commit()


async def read_usage(key_ids: list[int]) -> dict[int, tuple[int, int]]:
    """返回 {key_id: (今天, 近 7 天)}；Redis 不可用时全按 0。"""
    if not key_ids:
        return {}
    now = datetime.now(UTC)
    days = [now - timedelta(days=i) for i in range(7)]
    keys = [usage_key(k, d) for k in key_ids for d in days]
    try:
        r = await get_redis()
        values = await r.mget(keys)
    except Exception as e:
        logger.debug("API Key 用量读取失败: {!r}", e)
        values = [None] * len(keys)
    counts = [int(v) if v is not None else 0 for v in values]
    return {
        key_id: (counts[i * 7], sum(counts[i * 7 : i * 7 + 7])) for i, key_id in enumerate(key_ids)
    }


class ApiKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(self, user_id: int) -> list[ApiKey]:
        rows = await self.db.scalars(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.id.desc())
        )
        return list(rows)

    async def list_all(self) -> list[ApiKey]:
        rows = await self.db.scalars(
            select(ApiKey)
            .options(selectinload(ApiKey.user).selectinload(User.ea_bindings))
            .order_by(ApiKey.revoked_at.is_not(None), ApiKey.id.desc())
        )
        return list(rows)

    async def get(self, key_id: int, *, user_id: int | None = None) -> ApiKey:
        key = await self.db.get(ApiKey, key_id)
        if key is None or (user_id is not None and key.user_id != user_id):
            raise NotFoundError(resource=f"API Key {key_id}")
        return key

    async def create(self, user: User, name: str) -> tuple[ApiKey, str]:
        limit = get_settings().api_key_max_per_user
        active = await self.db.scalar(
            select(func.count())
            .select_from(ApiKey)
            .where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
        )
        if (active or 0) >= limit:
            raise ValidationError(f"每人最多 {limit} 个有效 API Key，先吊销不用的再新建")
        raw = KEY_PREFIX + secrets.token_urlsafe(32)
        key = ApiKey(user_id=user.id, name=name.strip(), prefix=raw[:12], key_hash=hash_key(raw))
        self.db.add(key)
        await self.db.commit()
        await self.db.refresh(key)
        return key, raw

    async def revoke(self, key: ApiKey) -> ApiKey:
        if key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(key)
            await self.drop_cache(key)
        return key

    async def set_multiplier(self, key: ApiKey, multiplier: int | None) -> ApiKey:
        key.rate_multiplier = multiplier
        await self.db.commit()
        await self.db.refresh(key)
        await self.drop_cache(key)
        return key

    async def drop_cache(self, key: ApiKey) -> None:
        try:
            r = await get_redis()
            await r.delete(_cache_key(key.key_hash))
        except Exception as e:
            # 删不掉也只是最多 60 秒后才生效
            logger.warning("API Key 缓存删除失败: {!r}", e)
