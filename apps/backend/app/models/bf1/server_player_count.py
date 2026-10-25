"""BF1 私服人数与地图采样时序"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1ServerPlayerCount(Base):
    __tablename__ = "bf1_server_player_counts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # game_id 仅定位当前这一局，服务器重启就会变
    game_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    # 快照带 PGID 时按它跨重启归并，否则退回按服名
    persisted_game_id: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    map_name: Mapped[str | None] = mapped_column(String(64))
    game_mode: Mapped[str | None] = mapped_column(String(32))

    player_count: Mapped[int] = mapped_column(nullable=False)
    queue_count: Mapped[int] = mapped_column(default=0, nullable=False)
    spectator_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_player_count: Mapped[int] = mapped_column(default=0, nullable=False)

    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    __table_args__ = (Index("ix_bf1_server_player_counts_name_time", "name", "sampled_at"),)
