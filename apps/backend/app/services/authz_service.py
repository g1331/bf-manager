"""服务器权限校验服务

权限判定优先级（自高而低）：
1. 平台 admin（user.role == "admin"）：绕过一切服务器级校验；
2. EA 服主 / 管理员自动识别：用户绑定的 persona 命中该服 EA 侧 owner → owner、
   命中 adminList → admin。识别成功即把该服登记为 Server（稳定 server_id + 末次 game_id）
   并 upsert 一条自动 ServerMembership（granted_by 为空），供「我的服务器」枚举；
3. 人工授权：平台 admin 经成员管理手动授予的 ServerMembership，作为委派 / 兜底。

注意：前端鉴权端点按 URL 的 game_id 寻址，而成员关系绑定在稳定的 server_id 上。
本服务统一在识别时经 EA 把 game_id 翻译成 server_id 再落库 / 查询，避免二者错配。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, ForbiddenError
from app.models import Server, ServerMembership, User
from app.services.bf1.server_service import BF1ServerService

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

    def _bound_persona_ids(self, user: User) -> set[int]:
        """user 当前可用（未冻结）的绑定 persona 集合"""
        return {b.persona_id for b in user.ea_bindings if not b.is_frozen}

    async def _upsert_server(
        self, *, game: str, server_id: int, game_id: int | None = None, name: str | None = None
    ) -> Server:
        """按稳定 server_id 查或建 Server，并回填末次 game_id / 名称（以 EA 为准）"""
        server = await self.db.scalar(
            select(Server).where(Server.game == game, Server.server_id == server_id)
        )
        if server is None:
            server = Server(game=game, server_id=server_id, game_id=game_id, name=name)
            self.db.add(server)
        else:
            if game_id is not None:
                server.game_id = game_id
            if name:
                server.name = name
        await self.db.commit()
        await self.db.refresh(server)
        return server

    async def _upsert_auto_membership(self, *, user_id: int, server_pk: int, role: str) -> None:
        """写入 / 更新自动识别出的成员关系。

        仅维护「自动」记录（granted_by 为空）：不存在则新建，存在且为自动记录时按 EA 现状更新角色；
        人工授权（granted_by 非空）一律不动，避免自动识别覆盖委派权限。
        """
        membership = await self.db.scalar(
            select(ServerMembership).where(
                ServerMembership.user_id == user_id,
                ServerMembership.server_pk == server_pk,
            )
        )
        if membership is None:
            self.db.add(
                ServerMembership(user_id=user_id, server_pk=server_pk, role=role, granted_by=None)
            )
            try:
                await self.db.commit()
            except IntegrityError:
                # 并发请求（如详情页 my-role 与一次操作同时触发）可能都读到 None 后各自插入，
                # 唯一约束 uq_server_memberships_user_server 让第二次冲突；视作幂等、回滚即可。
                await self.db.rollback()
        elif membership.granted_by is None and membership.role != role:
            membership.role = role
            await self.db.commit()

    async def _resolve_via_ea(
        self, *, user: User, game: str, game_id: int
    ) -> tuple[str | None, bool]:
        """按 EA 服主 / 管理员名单识别角色。

        返回 (role, handled)：handled=True 表示已成功取到该服的 EA 身份信息（无论是否命中），
        此时调用方应以本结果为准；handled=False 表示 EA 不可用 / 无绑定 / 非 RSP 服，
        调用方应走 legacy 回退。
        """
        persona_ids = self._bound_persona_ids(user)
        if not persona_ids:
            return None, False
        try:
            info = await BF1ServerService(self.db).get_admin_identity(game_id)
        except EAApiError:
            # 仅 EA 不可用（无账号 / 网关失败）时降级走 legacy 回退；其余异常（解析 bug 等）
            # 不吞，避免把代码缺陷伪装成「EA 不可用」而静默拒绝授权
            return None, False
        if info is None:
            return None, False
        owner_pid, admin_pids, server_id, name = info
        if not server_id:
            return None, False

        server = await self._upsert_server(
            game=game, server_id=server_id, game_id=game_id, name=name
        )
        if owner_pid is not None and owner_pid in persona_ids:
            role: str | None = "owner"
        elif persona_ids & set(admin_pids):
            role = "admin"
        else:
            role = None

        if role is not None:
            await self._upsert_auto_membership(user_id=user.id, server_pk=server.id, role=role)
            return role, True

        # 未命中 EA 名单：自动授予的记录（granted_by 为空）是 EA 状态的缓存，此刻应失效——
        # 用户已非该服 EA 服主 / 管理员，删除以保证撤权及「我的服务器」与 EA 现状一致
        # （若仅为 EA 短暂抽风，下次正确返回时会重新识别落库，自愈）。人工授权作为委派保留。
        membership = await self.db.scalar(
            select(ServerMembership).where(
                ServerMembership.user_id == user.id,
                ServerMembership.server_pk == server.id,
            )
        )
        if membership is not None and membership.granted_by is None:
            await self.db.delete(membership)
            await self.db.commit()
            membership = None
        return (membership.role if membership else None), True

    async def resolve_role(
        self,
        *,
        user: User,
        game: str,
        server_id: int,
    ) -> tuple[str | None, bool]:
        """取 user 对该服务器的角色，不抛错。

        形参 server_id 实为 URL 的 game_id（历史命名保持兼容）。返回 (role, is_platform_admin)：
        - 平台 admin：(None, True)，前端据此放开全部操作；
        - 其余：(role, False)，role 为 None 表示无任何服管权限。
        """
        if user.role == "admin":
            return None, True

        game_id = server_id
        role, handled = await self._resolve_via_ea(user=user, game=game, game_id=game_id)
        if handled:
            return role, False

        # EA 不可用时的 legacy 回退：按 game_id 当 server_id 查人工授权（多半不命中，等价旧行为）
        server = await self.db.scalar(
            select(Server).where(Server.game == game, Server.server_id == game_id)
        )
        if server is None:
            return None, False
        membership = await self.db.scalar(
            select(ServerMembership).where(
                ServerMembership.user_id == user.id,
                ServerMembership.server_pk == server.id,
            )
        )
        return (membership.role if membership else None), False

    async def require_role(
        self,
        *,
        user: User,
        game: str,
        server_id: int,
        min_role: str = "moderator",
    ) -> None:
        """校验 user 是否对该服务器具有至少 min_role 的权限，不足则抛 ForbiddenError。

        平台 admin 绕过所有服务器权限校验。
        """
        if user.role == "admin":
            return

        role, is_platform_admin = await self.resolve_role(user=user, game=game, server_id=server_id)
        if is_platform_admin:
            return
        if role is None:
            raise ForbiddenError(message="无权管理此服务器")
        if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL.get(min_role, 99):
            raise ForbiddenError(message=f"需要 {min_role} 及以上权限（当前 {role}）")
