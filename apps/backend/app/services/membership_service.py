"""ServerMembership 管理服务（仅平台 admin 调用）"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError, ValidationError
from app.models import Server, ServerMembership, User
from app.schemas.membership import MembershipItem

_ALLOWED_ROLES = {"viewer", "moderator", "admin", "owner"}


class MembershipService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self, *, game: str | None = None, page: int = 1, page_size: int = 50
    ) -> tuple[list[MembershipItem], int]:
        stmt = (
            select(ServerMembership, User, Server)
            .join(User, User.id == ServerMembership.user_id)
            .join(Server, Server.id == ServerMembership.server_pk)
            .order_by(ServerMembership.created_at.desc())
        )
        count_stmt = (
            select(func.count())
            .select_from(ServerMembership)
            .join(Server, Server.id == ServerMembership.server_pk)
        )
        if game:
            stmt = stmt.where(Server.game == game)
            count_stmt = count_stmt.where(Server.game == game)

        total = (await self.db.scalar(count_stmt)) or 0
        rows = (await self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).all()

        items = [
            MembershipItem(
                id=m.id,
                user_id=u.id,
                user_persona_id=u.persona_id,
                user_display_name=u.display_name,
                server_pk=s.id,
                game=s.game,
                server_id=s.server_id,
                server_name=s.name,
                role=m.role,  # type: ignore[arg-type]
                granted_by=m.granted_by,
                granted_at=m.created_at,
            )
            for m, u, s in rows
        ]
        return items, int(total)

    async def upsert(
        self,
        *,
        target_persona_id: int,
        game: str,
        server_id: int,
        role: str,
        granted_by_user: User,
    ) -> MembershipItem:
        if role not in _ALLOWED_ROLES:
            raise ValidationError(message=f"非法角色 {role}")

        target_user = await self.db.scalar(select(User).where(User.persona_id == target_persona_id))
        if target_user is None:
            raise NotFoundError(
                resource=f"persona {target_persona_id} 对应的用户（请让其先登录一次）"
            )

        server = await self.db.scalar(
            select(Server).where(Server.game == game, Server.server_id == server_id)
        )
        if server is None:
            server = Server(game=game, server_id=server_id)
            self.db.add(server)
            await self.db.flush()

        membership = await self.db.scalar(
            select(ServerMembership).where(
                ServerMembership.user_id == target_user.id,
                ServerMembership.server_pk == server.id,
            )
        )
        if membership is None:
            membership = ServerMembership(
                user_id=target_user.id,
                server_pk=server.id,
                role=role,
                granted_by=granted_by_user.id,
            )
            self.db.add(membership)
        else:
            membership.role = role
            membership.granted_by = granted_by_user.id

        await self.db.commit()
        await self.db.refresh(membership)

        return MembershipItem(
            id=membership.id,
            user_id=target_user.id,
            user_persona_id=target_user.persona_id,
            user_display_name=target_user.display_name,
            server_pk=server.id,
            game=server.game,
            server_id=server.server_id,
            server_name=server.name,
            role=membership.role,  # type: ignore[arg-type]
            granted_by=membership.granted_by,
            granted_at=membership.created_at,
        )

    async def delete(self, membership_id: int) -> None:
        membership = await self.db.scalar(
            select(ServerMembership).where(ServerMembership.id == membership_id)
        )
        if membership is None:
            raise NotFoundError(resource=f"权限记录 {membership_id}")
        await self.db.delete(membership)
        await self.db.commit()
