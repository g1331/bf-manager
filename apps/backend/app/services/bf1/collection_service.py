"""BF1 战绩页「收藏」分页：Gateway 的勋章、狗牌和当前佩戴的狗牌

一次 3 个 Gateway 请求，点开分页才查，按人缓存 1 天（解锁进度变化慢）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.core.cache import get_cache
from app.schemas.bf1.collection import CollectionDogtag, CollectionMedal, PlayerCollection
from app.services.bf1.gateway_factory import get_bf1_client

logger = logging.getLogger(__name__)

COLLECTION_CACHE_KEY = "bf1:collection:v1:{}"
COLLECTION_CACHE_TTL = 86400


def _progress(item: Any) -> dict[str, Any]:
    p = item.get("progression") if isinstance(item, dict) else None
    return p if isinstance(p, dict) else {}


def _groups(res: Any, items_key: str, method: str) -> list[dict[str, Any]]:
    """Gateway 返回 {"result": [{"name": 分类, items_key: [...]}, ...]}，展开成条目列表"""
    result = res.get("result") if isinstance(res, dict) else None
    if not isinstance(result, list):
        raise EAApiError(code="EA_COLLECTION_FETCH_FAILED", message=f"EA Gateway {method} 查询失败")
    return [
        x
        for g in result
        if isinstance(g, dict)
        for x in g.get(items_key) or []
        if isinstance(x, dict)
    ]


def _build_medals(res: Any) -> list[CollectionMedal]:
    medals = []
    for m in _groups(res, "awards", "getMedalsByPersonaId"):
        if not m.get("code"):
            continue
        stages = [s for s in m.get("stages") or [] if isinstance(s, dict)]
        medals.append(
            CollectionMedal(
                code=str(m["code"]).lower(),
                unlocked=bool(_progress(m).get("unlocked")),
                stages_done=sum(1 for s in stages if _progress(s).get("unlocked")),
                stages_total=len(stages),
            )
        )
    return medals


def _build_dogtags(res: Any) -> list[CollectionDogtag]:
    tags = []
    for t in _groups(res, "dogtags", "getDogtagsByPersonaId"):
        if not t.get("unlockId"):
            continue
        p = _progress(t)
        unlocked = bool(p.get("unlocked"))
        needed = p.get("valueNeeded")
        # 只要一次就解锁的没有进度可言
        has_progress = not unlocked and isinstance(needed, int | float) and needed > 1
        tags.append(
            CollectionDogtag(
                id=str(t["unlockId"]),
                unlocked=unlocked,
                acquired=p.get("valueAcquired") if has_progress else None,
                needed=needed if has_progress else None,
            )
        )
    return tags


def _build_equipped(res: Any) -> list[str]:
    """{"result": [狗牌, 狗牌]}：基本、高级各一块，字段同 getDogtagsByPersonaId 的条目"""
    result = res.get("result") if isinstance(res, dict) else None
    items = result if isinstance(result, list) else []
    return [str(x["unlockId"]) for x in items if isinstance(x, dict) and x.get("unlockId")]


async def get_collection(db: AsyncSession, persona_id: int) -> PlayerCollection:
    key = COLLECTION_CACHE_KEY.format(persona_id)
    cache = None
    try:
        cache = await get_cache()
        hit = await cache.get(key)
        if hit is not None:
            return PlayerCollection.model_validate(hit)
    except Exception as exc:
        logger.warning("BF1 收藏缓存读取失败 persona_id=%s: %s", persona_id, exc)
    async with get_bf1_client(db) as client:
        medals = await client.getMedalsByPersonaId(persona_id)
        dogtags = await client.getDogtagsByPersonaId(persona_id)
        try:
            equipped = _build_equipped(await client.getEquippedDogtagsByPersonaId(persona_id))
        except Exception as exc:  # 佩戴的狗牌只是装饰，读不到不影响整页
            logger.warning("BF1 佩戴狗牌查询失败 persona_id=%s: %s", persona_id, exc)
            equipped = []
    out = PlayerCollection(
        persona_id=persona_id,
        medals=_build_medals(medals),
        dogtags=_build_dogtags(dogtags),
        equipped=equipped,
    )
    if cache is not None:
        try:
            await cache.set(key, out.model_dump(mode="json"), ttl=COLLECTION_CACHE_TTL)
        except Exception as exc:
            logger.warning("BF1 收藏缓存写入失败 persona_id=%s: %s", persona_id, exc)
    return out
