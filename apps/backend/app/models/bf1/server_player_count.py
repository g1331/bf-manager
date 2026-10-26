"""BF1 私服人数与地图采样时序"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1ServerPlayerCount(Base):
    __tablename__ = "bf1_server_player_counts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # game_id 仅定位当前这一局，服务器重启就会变
    game_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    # RSP serverId，重启不变；由 gameId 问 Gateway 解析，解析到之前为空，此时按服名归并
    server_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    map_name: Mapped[str | None] = mapped_column(String(64))
    game_mode: Mapped[str | None] = mapped_column(String(32))

    player_count: Mapped[int] = mapped_column(nullable=False)
    queue_count: Mapped[int] = mapped_column(default=0, nullable=False)
    spectator_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_player_count: Mapped[int] = mapped_column(default=0, nullable=False)
    # 本轮名单相对上一轮进入 / 退出的人数；为空表示这一轮没拿到名单（快照失败回退了 searchServers）
    joined_count: Mapped[int | None] = mapped_column(SmallInteger)
    left_count: Mapped[int | None] = mapped_column(SmallInteger)

    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    __table_args__ = (Index("ix_bf1_server_player_counts_name_time", "name", "sampled_at"),)
