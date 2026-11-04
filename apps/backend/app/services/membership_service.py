"""ServerMembership 管理服务（仅平台 admin 调用）"""

from __future__ import annotations

import builtins
from typing import get_args

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError, ValidationError
from app.core.literals import MembershipRole
from app.models import (
    EaBinding,
    Group,
    GroupMember,
    GroupServer,
    Server,
    ServerMembership,
    User,
)
from app.schemas.bf1.admin import MyServerItem
from app.schemas.membership import MembershipItem
from app.services.authz_service import ROLE_LEVEL
from app.services.bf1.rsp_list_service import list_managed_servers

_ALLOWED_ROLES = set(get_args(MembershipRole))


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
        role=m.role,
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

    async def list_mine(self, *, user_id: int, game: str) -> builtins.list[MyServerItem]:
        """当前用户有服管角色的服务器列表（供「我的服务器」页面），最近授予在前。"""
        rows = (
            await self.db.execute(
                select(ServerMembership, Server)
                .join(Server, Server.id == ServerMembership.server_pk)
                .where(ServerMembership.user_id == user_id, Server.game == game)
                .order_by(ServerMembership.created_at.desc())
            )
        ).all()
        items = [
            MyServerItem(
                server_pk=s.id,
                game=s.game,
                server_id=s.server_id,
                game_id=s.game_id,
                name=s.name,
                role=m.role,
            )
            for m, s in rows
        ]
        # 挂在自己所在群上的服：群里的人在上面是管理员；已有直接角色的服不会更低，保留原样
        by_pk = {i.server_pk: i for i in items}
        user = await self.db.get(User, user_id)
        if user is None or (user.role != "admin" and user.status != "active"):
            return items
        group_rows = (
            await self.db.execute(
                select(Server, Group.name)
                .join(GroupServer, GroupServer.server_pk == Server.id)
                .join(Group, Group.id == GroupServer.group_id)
                .join(GroupMember, GroupMember.group_id == GroupServer.group_id)
                .where(
                    GroupMember.user_id == user_id,
                    GroupServer.status == "active",
                    Server.game == game,
                )
                .order_by(GroupServer.created_at.desc())
            )
        ).all()
        for s, group_name in group_rows:
            if s.id in by_pk:
                continue
            by_pk[s.id] = item = MyServerItem(
                server_pk=s.id,
                game=s.game,
                server_id=s.server_id,
                game_id=s.game_id,
                name=s.name,
                role="admin",
                via_group=group_name,
            )
            items.append(item)
        if game == "bf1":
            items.extend(await self._detected_bf1(user_id, {i.server_id for i in items}))
        return items

    async def _detected_bf1(self, user_id: int, known: set[int]) -> builtins.list[MyServerItem]:
        """收录的私服名单里，自己绑定的账号是服主或管理员、但还没识别落库的服。

        名单每台服几小时刷新一次，这里只用来列出来；真正操作时鉴权仍按 EA 实时名单走。
        """
        pids = await self._bound_personas(user_id)
        found: dict[int, tuple[str, int, str]] = {}
        for _, role, srv in await list_managed_servers(self.db, pids):
            if srv.server_id in known:
                continue
            prev = found.get(srv.server_id)
            if prev is None or ROLE_LEVEL[role] > ROLE_LEVEL[prev[0]]:
                found[srv.server_id] = (role, srv.game_id, srv.name)
        if not found:
            return []
        servers = {
            s.server_id: s
            for s in await self.db.scalars(
                select(Server).where(Server.game == "bf1", Server.server_id.in_(list(found)))
            )
        }
        # 还没建档的服先建档，列表项要 server_pk
        missing = [sid for sid in found if sid not in servers]
        for sid in missing:
            _, game_id, name = found[sid]
            servers[sid] = Server(game="bf1", server_id=sid, game_id=game_id, name=name)
            self.db.add(servers[sid])
        if missing:
            await self.db.commit()
        return [
            MyServerItem(
                server_pk=servers[sid].id,
                game="bf1",
                server_id=sid,
                game_id=game_id,
                name=name,
                role=role,
            )
            for sid, (role, game_id, name) in found.items()
        ]

    async def _bound_personas(self, user_id: int) -> set[int]:
        rows = await self.db.scalars(
            select(EaBinding.persona_id).where(
                EaBinding.user_id == user_id, EaBinding.is_frozen.is_(False)
            )
        )
        return set(rows.all())

    async def admin_server_ids(self, user: User) -> set[int]:
        """本地记录里这个人能以管理员以上身份管理的 BF1 私服（RSP serverId）：
        绑定账号在收录名单里是服主或管理员、人工授予管理员以上、或挂在自己所在的群上"""
        ids = {
            srv.server_id
            for _, _, srv in await list_managed_servers(
                self.db, await self._bound_personas(user.id)
            )
        }
        ids.update(
            await self.db.scalars(
                select(Server.server_id)
                .join(ServerMembership, ServerMembership.server_pk == Server.id)
                .where(
                    ServerMembership.user_id == user.id,
                    ServerMembership.role.in_(("admin", "owner")),
                    Server.game == "bf1",
                )
            )
        )
        if not user.is_frozen and (user.role == "admin" or user.status == "active"):
            ids.update(
                await self.db.scalars(
                    select(Server.server_id)
                    .join(GroupServer, GroupServer.server_pk == Server.id)
                    .join(GroupMember, GroupMember.group_id == GroupServer.group_id)
                    .where(
                        GroupMember.user_id == user.id,
                        GroupServer.status == "active",
                        Server.game == "bf1",
                    )
                )
            )
        return ids

    async def upsert(
        self,
        *,
        target_persona_id: int,
        game: str,
        server_id: int,
        role: MembershipRole,
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
