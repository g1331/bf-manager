"""BF1 私服的服主 / 管理 / VIP / 封禁名单，按玩家反查他在哪些服有身份（天眼查）"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1RspServer(Base):
    """收录了名单的服务器，按 RSP serverId 记，重启换 gameId 也是同一行。"""

    __tablename__ = "bf1_rsp_servers"

    server_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 最近一次看到的实例，详情页按它跳转
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 名单最近一次从 EA 拉到的时间；长期没刷新的服视为已关服，连名单一起清掉
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class Bf1RspMember(Base):
    """名单里的一个人。role 取 owner / admin / vip / ban，每次刷新整服替换。"""

    __tablename__ = "bf1_rsp_members"

    server_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bf1_rsp_servers.server_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(8), primary_key=True)
    pid: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    # 拉名单时 EA 给的名字，改名后会过时，仅作展示
    name: Mapped[str | None] = mapped_column(String(64))
