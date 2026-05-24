"""BF1 对局缓存"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1MatchIdCache(Base):
    """玩家 → 最近对局 ID 列表的缓存索引"""

    __tablename__ = "bf1_match_id_caches"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    match_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_bf1_match_id_caches_persona", "persona_id"),)


class Bf1Match(Base):
    """对局详细数据缓存（JSON 全量字段）"""

    __tablename__ = "bf1_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_seconds: Mapped[int] = mapped_column(default=0, nullable=False)

    map_name: Mapped[str | None] = mapped_column(String(64))
    game_mode: Mapped[str | None] = mapped_column(String(64))
    server_name: Mapped[str | None] = mapped_column(String(255))

    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
