"""BF1 交换（ScrapExchange）与行动（CampaignOperations）

交换每周轮换一次。后台每小时问一次 EA，物品清单（key + 价格）与库里最新一期不同就记为新的一期，
历史交换就是这张表；2022-07 至 2025-06 的旧存档由 tools/import_bf1_exchange.py 从 umrbot 导入。
行动没有历史需求，实时查询并短暂缓存。EA 只返回繁体，这里统一转简体。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from zhconv import zhconv

from app.api.errors import EAApiError, NotFoundError
from app.core import ea_metrics
from app.core.cache import get_cache
from app.db.session import get_sessionmaker
from app.domain.games.bf1.maps import normalize_map_image_url
from app.models.bf1.exchange import Bf1ExchangeSnapshot
from app.schemas.bf1.exchange import (
    Campaign,
    CampaignOperation,
    ExchangeItem,
    ExchangeSnapshot,
)
from app.services.bf1.gateway_factory import get_bf1_client

# 交换按北京时间的日期查询，旧存档的文件名也是北京时间日期
CN_TZ = ZoneInfo("Asia/Shanghai")
EXCHANGE_POLL_SECONDS = 60 * 60
CAMPAIGN_CACHE_KEY = "bf1:campaign"
CAMPAIGN_CACHE_TTL = 10 * 60
# 没有所属武器的物品，EA 给的分类是未翻译的代号（如 ID_P_CAT_MELEE、Unknown: mlara_v），没列出的不展示
CATEGORY_NAMES = {"ID_P_CAT_MELEE": "近战武器", "ID_P_CAT_XPBOOST": "经验加成"}


def _cn(text: str | None) -> str:
    return zhconv.convert(text or "", "zh-cn")


def offers_signature(items: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """判断两期是否相同只看物品 key 与价格；ownedQuantity 等字段随查询账号变化，不能参与比较。"""
    return sorted((str(i["item"]["key"]), int(i["price"])) for i in items)


def to_exchange_item(raw: dict[str, Any]) -> ExchangeItem:
    item = raw["item"]
    category = item.get("category") or ""
    return ExchangeItem(
        key=item["key"],
        name=_cn(item.get("name")),
        parent_name=_cn(item.get("parentName")) or None,
        category=CATEGORY_NAMES.get(category, None if category.isascii() else _cn(category))
        or None,
        rarity=(item.get("rarenessLevel") or {}).get("name") or "Standard",
        price=int(raw["price"]),
        image_url=normalize_map_image_url((item.get("images") or {}).get("Png300xANY")),
    )


def _to_snapshot(row: Bf1ExchangeSnapshot) -> ExchangeSnapshot:
    return ExchangeSnapshot(
        captured_at=row.captured_at, items=[to_exchange_item(i) for i in row.items]
    )


async def save_exchange_if_changed(
    db: AsyncSession, items: list[dict[str, Any]], captured_at: datetime
) -> bool:
    """与 captured_at 之前最近一期比较，物品有变化才新增一期。返回是否写入。"""
    prev = await db.scalar(
        select(Bf1ExchangeSnapshot)
        .where(Bf1ExchangeSnapshot.captured_at <= captured_at)
        .order_by(Bf1ExchangeSnapshot.captured_at.desc())
        .limit(1)
    )
    if prev is not None and (
        prev.captured_at == captured_at or offers_signature(prev.items) == offers_signature(items)
    ):
        return False
    db.add(Bf1ExchangeSnapshot(captured_at=captured_at, items=items))
    await db.commit()
    return True


async def refresh_exchange(db: AsyncSession) -> bool:
    async with get_bf1_client(db) as client:
        res = await client.getOffers()
    items = (res.get("result") or {}).get("items") if isinstance(res, dict) else None
    if not items:
        raise EAApiError(code="EA_EXCHANGE_FETCH_FAILED", message=f"EA 交换查询失败: {res}")
    return await save_exchange_if_changed(db, items, datetime.now(UTC))


async def exchange_poller() -> None:
    """后台定时轮询交换。在应用 lifespan 中以 asyncio 任务启动。"""
    ea_metrics.set_source("exchange")
    while True:
        try:
            async with get_sessionmaker()() as db:
                if await refresh_exchange(db):
                    logger.info("BF1 exchange: new period recorded")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("BF1 exchange poll failed: {}", e)
        await asyncio.sleep(EXCHANGE_POLL_SECONDS)


async def get_exchange(db: AsyncSession, on: date | None = None) -> ExchangeSnapshot:
    """返回 on 当天（北京时间）生效的那一期；不传为最新一期。"""
    stmt = select(Bf1ExchangeSnapshot).order_by(Bf1ExchangeSnapshot.captured_at.desc()).limit(1)
    if on is not None:
        day_end = datetime.combine(on + timedelta(days=1), time(), tzinfo=CN_TZ).astimezone(UTC)
        stmt = stmt.where(Bf1ExchangeSnapshot.captured_at < day_end)
    row = await db.scalar(stmt)
    if row is None:
        raise NotFoundError("该日期的交换记录")
    return _to_snapshot(row)


async def list_exchange_periods(db: AsyncSession) -> list[datetime]:
    return list(
        await db.scalars(
            select(Bf1ExchangeSnapshot.captured_at).order_by(Bf1ExchangeSnapshot.captured_at.desc())
        )
    )


def to_campaign(result: dict[str, Any], now: datetime) -> Campaign:
    ops = [result.get(f"op{i}") for i in range(1, 6)]
    return Campaign(
        name=_cn(result.get("name")),
        description=_cn(result.get("shortDesc")).strip(),
        ends_at=now + timedelta(minutes=int(result.get("minutesRemaining") or 0)),
        daily_reset_at=now + timedelta(minutes=int(result.get("minutesToDailyReset") or 0)),
        operations=[
            CampaignOperation(
                name=_cn(op.get("name")), image_url=normalize_map_image_url(op.get("imageUrl"))
            )
            for op in ops
            if op
        ],
    )


async def get_campaign(db: AsyncSession) -> Campaign | None:
    """当前行动；EA 没有进行中的行动时为 None。缓存的是绝对时间，过期前不会走样。"""
    cache = await get_cache()
    cached = await cache.get(CAMPAIGN_CACHE_KEY)
    if cached is not None:
        return Campaign.model_validate(cached) if cached else None
    async with get_bf1_client(db) as client:
        res = await client.getPlayerCampaignStatus()
    if not isinstance(res, dict):
        raise EAApiError(code="EA_CAMPAIGN_FETCH_FAILED", message=f"EA 行动查询失败: {res}")
    result = res.get("result")
    campaign = to_campaign(result, datetime.now(UTC)) if result else None
    await cache.set(
        CAMPAIGN_CACHE_KEY, campaign.model_dump(mode="json") if campaign else {}, CAMPAIGN_CACHE_TTL
    )
    return campaign
