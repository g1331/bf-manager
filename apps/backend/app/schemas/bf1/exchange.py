"""BF1 交换与行动的响应模型"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ExchangeItem(BaseModel):
    key: str
    name: str
    # 皮肤所属武器 / 载具，非皮肤物品为空
    parent_name: str | None = None
    category: str | None = None
    # EA rarenessLevel.name：Superior / Enhanced / Standard
    rarity: str
    price: int
    image_url: str | None = None


class ExchangeSnapshot(BaseModel):
    captured_at: datetime
    items: list[ExchangeItem]


class CampaignOperation(BaseModel):
    name: str
    image_url: str | None = None


class Campaign(BaseModel):
    name: str
    description: str
    ends_at: datetime
    daily_reset_at: datetime
    operations: list[CampaignOperation]
