"""BF1 服务器实例：一个 gameId 就是服务器的一次开服"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1GameInstance(Base):
    """gameId 在一次开服期间不变，重启后换新的，所以人数点、名单等按它写，读时再按服务器归并。

    有服主的服（私服，以及 servertype 为 OFFICIAL 但有 owner 的租用服）重启后由 RSP serverId
    串起来；真官服（owner 为 0）没有持久身份，一个实例就是一台服务器。
    """

    __tablename__ = "bf1_game_instances"

    game_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # RSP serverId，由 gameId 问 Gateway 解析，解析到之前为空；真官服恒为空
    server_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    official: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # 最近一次看到的服名
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
