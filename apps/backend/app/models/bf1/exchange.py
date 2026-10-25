"""BF1 交换（ScrapExchange）每期快照"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1ExchangeSnapshot(Base):
    __tablename__ = "bf1_exchange_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 本期首次被记录的时间；导入的旧存档只有日期，按北京时间当天 0 点记
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), unique=True, index=True, nullable=False
    )
    # EA ScrapExchange.getOffers 原样的 result.items，展示时再规整
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
