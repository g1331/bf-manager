"""BF1 服管操作服务"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.domain.games.bf1.client_provider import BF1ClientProvider, PooledBF1ClientProvider
from app.models import User
from app.services.audit_service import AuditService
from app.services.authz_service import ServerAuthzService


def _ensure_dict_or_raise(data: Any, error_code: str) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    raise EAApiError(code=error_code, message=str(data)[:256])


class BF1ServerAdminService:
    """BF1 服管操作 + 审计写入。

    所有方法约定：
    - 调用前已通过 ServerAuthzService.require_role 校验
    - 执行 EA API 后自动写 audit_logs
    - 失败时 audit_logs.result='failure'，并向上抛出 EAApiError
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        user: User,
        game_id: int,
        request_meta: dict[str, str | None] | None = None,
        client_provider: BF1ClientProvider | None = None,
    ) -> None:
        self.db = db
        self.user = user
        self.game_id = game_id
        self.audit = AuditService(db)
        self.authz = ServerAuthzService(db)
        # 默认走后台账号池；未来引入按发起者 / 群组路由的 provider 时由路由层注入替换。
        # 详见 https://github.com/g1331/bf-manager/issues/1
        self.client_provider: BF1ClientProvider = client_provider or PooledBF1ClientProvider(db)
        meta = request_meta or {}
        self.ip = meta.get("ip")
        self.user_agent = meta.get("user_agent")
        # 审计 acting_persona_id 取自当前用户的 primary 未冻结 binding（已被 get_current_user
        # 通过 selectinload eager-load 到 user.ea_bindings 上），无可用 binding 时写 0
        self._acting_persona_id = next(
            (b.persona_id for b in user.ea_bindings if b.is_primary and not b.is_frozen),
            0,
        )

    async def _audit_success(
        self, action: str, payload: dict[str, Any], target_persona_id: int | None = None
    ) -> None:
        await self.audit.record(
            user_id=self.user.id,
            acting_persona_id=self._acting_persona_id,
            game="bf1",
            action=action,
            server_id=self.game_id,
            target_persona_id=target_persona_id,
            payload=payload,
            result="success",
            ip=self.ip,
            user_agent=self.user_agent,
        )

    async def _audit_failure(
        self,
        action: str,
        payload: dict[str, Any],
        error: EAApiError,
        target_persona_id: int | None = None,
    ) -> None:
        await self.audit.record(
            user_id=self.user.id,
            acting_persona_id=self._acting_persona_id,
            game="bf1",
            action=action,
            server_id=self.game_id,
            target_persona_id=target_persona_id,
            payload=payload,
            result="failure",
            error_code=error.code,
            error_message=error.message,
            ip=self.ip,
            user_agent=self.user_agent,
        )

    async def kick_player(self, persona_id: int, reason: str) -> dict[str, Any]:
        payload = {"persona_id": persona_id, "reason": reason}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.kickPlayer(self.game_id, persona_id, reason)
                data = _ensure_dict_or_raise(res, "EA_KICK_FAILED")
            await self._audit_success("kick_player", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("kick_player", payload, err, target_persona_id=persona_id)
            raise

    async def move_player(self, persona_id: int, team_id: int) -> dict[str, Any]:
        """把玩家换到对面阵营（换边）。

        RSP.movePlayer 的 teamId 语义是玩家「当前所在队伍」的队伍号（1-based）：传入源
        队伍号，引擎会把该玩家移动到另一队。Blaze 实时名单里的 team 是 0/1（TIDX），因此
        rsp_team = team_id + 1。换边总是 toggle 到对面，故只需玩家当前队伍号即可。
        与 kick 一致用 game_id 寻址（不是 ea_server_id）。
        """
        rsp_team = team_id + 1
        payload = {"persona_id": persona_id, "team_id": team_id, "rsp_team": rsp_team}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.movePlayer(self.game_id, persona_id, rsp_team)
                data = _ensure_dict_or_raise(res, "EA_MOVE_FAILED")
            await self._audit_success("move_player", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("move_player", payload, err, target_persona_id=persona_id)
            raise

    async def add_ban(self, persona_id: int, ea_server_id: int) -> dict[str, Any]:
        """添加 ban（用 EA serverId，不是 game_id）"""
        payload = {"persona_id": persona_id, "server_id": ea_server_id}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.addServerBan(persona_id, ea_server_id)
                data = _ensure_dict_or_raise(res, "EA_ADD_BAN_FAILED")
            await self._audit_success("add_ban", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("add_ban", payload, err, target_persona_id=persona_id)
            raise

    async def remove_ban(self, persona_id: int, ea_server_id: int) -> dict[str, Any]:
        payload = {"persona_id": persona_id, "server_id": ea_server_id}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.removeServerBan(persona_id, ea_server_id)
                data = _ensure_dict_or_raise(res, "EA_REMOVE_BAN_FAILED")
            await self._audit_success("remove_ban", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("remove_ban", payload, err, target_persona_id=persona_id)
            raise

    async def add_vip(self, persona_id: int, ea_server_id: int) -> dict[str, Any]:
        payload = {"persona_id": persona_id, "server_id": ea_server_id}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.addServerVip(persona_id, ea_server_id)
                data = _ensure_dict_or_raise(res, "EA_ADD_VIP_FAILED")
            await self._audit_success("add_vip", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("add_vip", payload, err, target_persona_id=persona_id)
            raise

    async def remove_vip(self, persona_id: int, ea_server_id: int) -> dict[str, Any]:
        payload = {"persona_id": persona_id, "server_id": ea_server_id}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.removeServerVip(persona_id, ea_server_id)
                data = _ensure_dict_or_raise(res, "EA_REMOVE_VIP_FAILED")
            await self._audit_success("remove_vip", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("remove_vip", payload, err, target_persona_id=persona_id)
            raise

    async def add_admin(self, persona_id: int, ea_server_id: int) -> dict[str, Any]:
        payload = {"persona_id": persona_id, "server_id": ea_server_id}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.addServerAdmin(persona_id, ea_server_id)
                data = _ensure_dict_or_raise(res, "EA_ADD_ADMIN_FAILED")
            await self._audit_success("add_admin", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("add_admin", payload, err, target_persona_id=persona_id)
            raise

    async def remove_admin(self, persona_id: int, ea_server_id: int) -> dict[str, Any]:
        payload = {"persona_id": persona_id, "server_id": ea_server_id}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.removeServerAdmin(persona_id, ea_server_id)
                data = _ensure_dict_or_raise(res, "EA_REMOVE_ADMIN_FAILED")
            await self._audit_success("remove_admin", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("remove_admin", payload, err, target_persona_id=persona_id)
            raise

    async def choose_level(self, persisted_game_id: str, level_index: int) -> dict[str, Any]:
        payload = {"persisted_game_id": persisted_game_id, "level_index": level_index}
        try:
            async with self.client_provider.acquire() as client:
                res = await client.chooseLevel(persisted_game_id, level_index)
                data = _ensure_dict_or_raise(res, "EA_CHOOSE_LEVEL_FAILED")
            await self._audit_success("choose_level", payload)
            return data
        except EAApiError as err:
            await self._audit_failure("choose_level", payload, err)
            raise
