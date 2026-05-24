"""BF1 服务器人数变化时序"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1ServerPlayerCount(Base):
    __tablename__ = "bf1_server_player_counts"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), nullable=False
    )

    player_count: Mapped[int] = mapped_column(nullable=False)
    queue_count: Mapped[int] = mapped_column(default=0, nullable=False)
    spectator_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_player_count: Mapped[int] = mapped_column(default=0, nullable=False)

    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_bf1_server_player_counts_server_time", "server_pk", "sampled_at"),)
