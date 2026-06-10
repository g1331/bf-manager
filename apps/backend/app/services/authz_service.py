"""服务器权限校验服务"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ForbiddenError, NotFoundError
from app.models import Server, ServerMembership, User

# 角色等级映射（数值越大权限越高）
ROLE_LEVEL = {
    "viewer": 1,
    "moderator": 2,
    "admin": 3,
    "owner": 4,
}


class ServerAuthzService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_register_server(self, *, game: str, server_id: int) -> Server:
        """按 game + EA serverId 查或注册一条服务器记录"""
        stmt = select(Server).where(Server.game == game, Server.server_id == server_id)
        server = await self.db.scalar(stmt)
        if server is None:
            server = Server(game=game, server_id=server_id)
            self.db.add(server)
            await self.db.commit()
            await self.db.refresh(server)
        return server

    async def require_role(
        self,
        *,
        user: User,
        game: str,
        server_id: int,
        min_role: str = "moderator",
    ) -> Server:
        """校验 user 是否对该服务器具有至少 min_role 的权限。

        平台 admin 角色绕过所有服务器权限校验。
        """
        if user.role == "admin":
            return await self.get_or_register_server(game=game, server_id=server_id)

        server = await self.db.scalar(
            select(Server).where(Server.game == game, Server.server_id == server_id)
        )
        if server is None:
            raise NotFoundError(resource=f"服务器 {server_id}")

        membership = await self.db.scalar(
            select(ServerMembership).where(
                ServerMembership.user_id == user.id,
                ServerMembership.server_pk == server.id,
            )
        )
        if membership is None:
            raise ForbiddenError(message="无权管理此服务器")

        if ROLE_LEVEL.get(membership.role, 0) < ROLE_LEVEL.get(min_role, 99):
            raise ForbiddenError(message=f"需要 {min_role} 及以上权限（当前 {membership.role}）")
        return server

    async def resolve_role(
        self,
        *,
        user: User,
        game: str,
        server_id: int,
    ) -> tuple[str | None, bool]:
        """取 user 对该服务器的角色，不抛错。

        用于前端按角色 gating 内联服管操作。返回 (role, is_platform_admin)：
        - 平台 admin：(None, True)，前端据此放开全部操作；
        - 服务器尚未注册或用户无成员记录：(None, False)；
        - 其余：(membership.role, False)。
        """
        if user.role == "admin":
            return None, True

        server = await self.db.scalar(
            select(Server).where(Server.game == game, Server.server_id == server_id)
        )
        if server is None:
            return None, False

        membership = await self.db.scalar(
            select(ServerMembership).where(
                ServerMembership.user_id == user.id,
                ServerMembership.server_pk == server.id,
            )
        )
        if membership is None:
            return None, False
        return membership.role, False
