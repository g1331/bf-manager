"""跨游戏服务器登记表 + 用户服管权限表"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Server(Base, TimestampMixin):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 游戏标识：'bf1' / 'bfv' / 'bf2042'
    game: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    # EA serverId（与 game 组合唯一）
    server_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    persisted_game_id: Mapped[str | None] = mapped_column(String(64), index=True)

    name: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("game", "server_id", name="uq_servers_game_server_id"),)


class ServerMembership(Base, TimestampMixin):
    """用户对服务器的管理权"""

    __tablename__ = "server_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # owner / admin / moderator / viewer
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("user_id", "server_pk", name="uq_server_memberships_user_server"),
    )
