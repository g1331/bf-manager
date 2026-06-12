"""BF1 服管操作服务"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, ForbiddenError
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
        # 默认走后台账号池；服管路由层注入 BindingFirstBF1ClientProvider 实现
        # 「发起者 binding 优先、账号池兜底」（https://github.com/g1331/bf-manager/issues/1）。
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

    def _tag_credential_source(self, payload: dict[str, Any]) -> None:
        """把本次实际使用的凭据来源写进审计 payload（用于排查 binding 降级）。

        credential_source 属性不属于 BF1ClientProvider Protocol，软读取保证
        旧 provider / 测试 fake 兼容；acquire 进入前抛错（如池空）时不会被调用，
        payload 不带该键，语义为「来源未知」。
        """
        source = getattr(self.client_provider, "credential_source", None)
        if source is not None:
            payload["credential_source"] = source

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

    async def _resolve_ea_ids(self, client: Any) -> tuple[int | None, str | None]:
        """按 game_id 实时解析本服的 EA RSP serverId 与 persistedGameId。

        servers 表的 server_id 列存的是平台权限映射用的 gameId（路由路径参数），
        不是 RSP 名单操作要的 serverId；persisted_game_id 列也没有回填链路。
        两个标识均以 getFullServerDetails 服务端实时解析为准（与详情页解析同源），
        不信任客户端传值，横向越权结构性消除。
        """
        res = await client.getFullServerDetails(self.game_id)
        data = _ensure_dict_or_raise(res, "EA_SERVER_DETAIL_FAILED")
        raw = data.get("result") or {}
        server_info = raw.get("serverInfo") or {}
        rsp_server = (raw.get("rspInfo") or {}).get("server") or {}
        server_id_raw = rsp_server.get("serverId") or server_info.get("serverId")
        try:
            server_id = int(server_id_raw) if server_id_raw is not None else None
        except (TypeError, ValueError):
            server_id = None
        persisted_game_id = (
            server_info.get("persistedGameId")
            or raw.get("persistedGameId")
            or server_info.get("guid")
        )
        return server_id, persisted_game_id

    async def _resolve_rsp_server_id(self, client: Any) -> int:
        server_id, _ = await self._resolve_ea_ids(client)
        if not server_id:
            raise EAApiError(
                code="EA_RSP_SERVER_ID_MISSING",
                message="无法获取该服务器的 RSP serverId，请稍后重试",
            )
        return server_id

    async def kick_player(self, persona_id: int, reason: str) -> dict[str, Any]:
        payload = {"persona_id": persona_id, "reason": reason}
        try:
            async with self.client_provider.acquire() as client:
                self._tag_credential_source(payload)
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
                self._tag_credential_source(payload)
                res = await client.movePlayer(self.game_id, persona_id, rsp_team)
                data = _ensure_dict_or_raise(res, "EA_MOVE_FAILED")
            await self._audit_success("move_player", payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure("move_player", payload, err, target_persona_id=persona_id)
            raise

    async def _member_op(
        self, action: str, ea_method: str, error_code: str, persona_id: int
    ) -> dict[str, Any]:
        """RSP 名单操作（封禁 / VIP / 管理员增删）的共用执行体。

        名单操作以 RSP serverId 寻址（不是 game_id，错传时 EA 返回
        InvalidServerIdException），执行前在同一连接上实时解析。
        """
        payload: dict[str, Any] = {"persona_id": persona_id}
        try:
            async with self.client_provider.acquire() as client:
                self._tag_credential_source(payload)
                ea_server_id = await self._resolve_rsp_server_id(client)
                payload["server_id"] = ea_server_id
                res = await getattr(client, ea_method)(persona_id, ea_server_id)
                data = _ensure_dict_or_raise(res, error_code)
            await self._audit_success(action, payload, target_persona_id=persona_id)
            return data
        except EAApiError as err:
            await self._audit_failure(action, payload, err, target_persona_id=persona_id)
            raise

    async def add_ban(self, persona_id: int) -> dict[str, Any]:
        return await self._member_op("add_ban", "addServerBan", "EA_ADD_BAN_FAILED", persona_id)

    async def remove_ban(self, persona_id: int) -> dict[str, Any]:
        return await self._member_op(
            "remove_ban", "removeServerBan", "EA_REMOVE_BAN_FAILED", persona_id
        )

    async def add_vip(self, persona_id: int) -> dict[str, Any]:
        return await self._member_op("add_vip", "addServerVip", "EA_ADD_VIP_FAILED", persona_id)

    async def remove_vip(self, persona_id: int) -> dict[str, Any]:
        return await self._member_op(
            "remove_vip", "removeServerVip", "EA_REMOVE_VIP_FAILED", persona_id
        )

    async def add_admin(self, persona_id: int) -> dict[str, Any]:
        return await self._member_op(
            "add_admin", "addServerAdmin", "EA_ADD_ADMIN_FAILED", persona_id
        )

    async def remove_admin(self, persona_id: int) -> dict[str, Any]:
        return await self._member_op(
            "remove_admin", "removeServerAdmin", "EA_REMOVE_ADMIN_FAILED", persona_id
        )

    async def choose_level(self, level_index: int) -> dict[str, Any]:
        """换图。目标 persistedGameId 由服务端实时解析，不接受客户端传值。

        EA 详情尚无 persistedGameId（服务器未完成初始化）时 fail-closed 拒绝，
        不触达 chooseLevel。
        """
        payload: dict[str, Any] = {"level_index": level_index}
        try:
            async with self.client_provider.acquire() as client:
                self._tag_credential_source(payload)
                _, persisted_game_id = await self._resolve_ea_ids(client)
                if not persisted_game_id:
                    raise ForbiddenError(message="服务器尚未完成初始化，无法执行换图操作")
                payload["persisted_game_id"] = persisted_game_id
                res = await client.chooseLevel(persisted_game_id, level_index)
                data = _ensure_dict_or_raise(res, "EA_CHOOSE_LEVEL_FAILED")
            await self._audit_success("choose_level", payload)
            return data
        except EAApiError as err:
            await self._audit_failure("choose_level", payload, err)
            raise
