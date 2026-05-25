"""ServerMembership 管理服务（仅平台 admin 调用）"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError, ValidationError
from app.models import EaBinding, Server, ServerMembership, User
from app.schemas.membership import MembershipItem

_ALLOWED_ROLES = {"viewer", "moderator", "admin", "owner"}


def _primary_binding(user: User) -> EaBinding | None:
    """从 user.ea_bindings 中取 primary（要求调用方已 eager-load）"""
    for b in user.ea_bindings:
        if b.is_primary:
            return b
    return None


def _build_item(m: ServerMembership, u: User, s: Server) -> MembershipItem:
    primary = _primary_binding(u)
    return MembershipItem(
        id=m.id,
        user_id=u.id,
        user_username=u.username,
        user_persona_id=primary.persona_id if primary is not None else None,
        user_display_name=primary.display_name if primary is not None else None,
        server_pk=s.id,
        game=s.game,
        server_id=s.server_id,
        server_name=s.name,
        role=m.role,  # type: ignore[arg-type]
        granted_by=m.granted_by,
        granted_at=m.created_at,
    )


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
            .options(selectinload(User.ea_bindings))
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

        items = [_build_item(m, u, s) for m, u, s in rows]
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

        target_user = await self.db.scalar(
            select(User)
            .join(EaBinding, EaBinding.user_id == User.id)
            .where(EaBinding.persona_id == target_persona_id)
            .options(selectinload(User.ea_bindings))
        )
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
        return _build_item(membership, target_user, server)

    async def delete(self, membership_id: int) -> None:
        membership = await self.db.scalar(
            select(ServerMembership).where(ServerMembership.id == membership_id)
        )
        if membership is None:
            raise NotFoundError(resource=f"权限记录 {membership_id}")
        await self.db.delete(membership)
        await self.db.commit()
