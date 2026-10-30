"""BF1 服务器人数与地图采样时序"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1ServerPlayerCount(Base):
    __tablename__ = "bf1_server_player_counts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 服务器实例，重启就会变；服名与 serverId 记在 bf1_game_instances，读时按它归并
    game_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    map_name: Mapped[str | None] = mapped_column(String(64))
    game_mode: Mapped[str | None] = mapped_column(String(32))

    player_count: Mapped[int] = mapped_column(nullable=False)
    queue_count: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    spectator_count: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    max_player_count: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    # 本轮名单相对上一轮进入 / 退出的人数；为空表示这一轮没拿到名单（快照失败回退了 searchServers）
    joined_count: Mapped[int | None] = mapped_column(SmallInteger)
    left_count: Mapped[int | None] = mapped_column(SmallInteger)

    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
