"""BF1 服管操作路由（需登录 + 服务器权限）"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbDep
from app.api.errors import ForbiddenError
from app.schemas.bf1.admin import (
    AdminActionResult,
    BanPlayerRequest,
    ChooseLevelRequest,
    KickPlayerRequest,
    MyServerRoleResult,
    ServerMemberRequest,
)
from app.services.authz_service import ServerAuthzService
from app.services.bf1.server_admin_service import BF1ServerAdminService

router = APIRouter()


def _request_meta(request: Request) -> dict[str, str | None]:
    client = request.client
    return {
        "ip": client.host if client else None,
        "user_agent": request.headers.get("user-agent"),
    }


def _admin_service(
    db: DbDep,
    request: Request,
    user: CurrentUser,
    game_id: int,
) -> BF1ServerAdminService:
    return BF1ServerAdminService(
        db,
        user=user,
        game_id=game_id,
        request_meta=_request_meta(request),
    )


@router.get("/{game_id}/my-role", response_model=MyServerRoleResult)
async def my_server_role(
    game_id: int,
    db: DbDep,
    user: CurrentUser,
) -> MyServerRoleResult:
    """返回当前登录用户对该服务器的角色，仅需登录、不要求任何角色。

    前端据此 gating 内联服管操作（踢人 / 封禁 / VIP / 换图等），无角色则不渲染入口。
    """
    authz = ServerAuthzService(db)
    role, is_platform_admin = await authz.resolve_role(user=user, game="bf1", server_id=game_id)
    return MyServerRoleResult(role=role, is_platform_admin=is_platform_admin)


@router.post("/{game_id}/kick", response_model=AdminActionResult)
async def kick_player(
    game_id: int,
    payload: KickPlayerRequest,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="moderator")
    service = _admin_service(db, request, user, game_id)
    await service.kick_player(payload.persona_id, payload.reason)
    return AdminActionResult(success=True, message=f"已踢出玩家 {payload.persona_id}")


@router.post("/{game_id}/ban", response_model=AdminActionResult)
async def add_ban(
    game_id: int,
    payload: BanPlayerRequest,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    server = await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="admin")
    service = _admin_service(db, request, user, game_id)
    await service.add_ban(payload.persona_id, server.server_id)
    return AdminActionResult(success=True, message=f"已封禁玩家 {payload.persona_id}")


@router.delete("/{game_id}/ban/{persona_id}", response_model=AdminActionResult)
async def remove_ban(
    game_id: int,
    persona_id: int,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    server = await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="admin")
    service = _admin_service(db, request, user, game_id)
    await service.remove_ban(persona_id, server.server_id)
    return AdminActionResult(success=True, message=f"已解除玩家 {persona_id} 的封禁")


@router.post("/{game_id}/vip", response_model=AdminActionResult)
async def add_vip(
    game_id: int,
    payload: ServerMemberRequest,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    server = await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="admin")
    service = _admin_service(db, request, user, game_id)
    await service.add_vip(payload.persona_id, server.server_id)
    return AdminActionResult(success=True, message=f"已添加 VIP {payload.persona_id}")


@router.delete("/{game_id}/vip/{persona_id}", response_model=AdminActionResult)
async def remove_vip(
    game_id: int,
    persona_id: int,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    server = await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="admin")
    service = _admin_service(db, request, user, game_id)
    await service.remove_vip(persona_id, server.server_id)
    return AdminActionResult(success=True, message=f"已移除 VIP {persona_id}")


# 管理员名单的增减比 VIP 更敏感，限定服主（owner）级别，避免管理员互相增删。
@router.post("/{game_id}/admin", response_model=AdminActionResult)
async def add_admin(
    game_id: int,
    payload: ServerMemberRequest,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    server = await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="owner")
    service = _admin_service(db, request, user, game_id)
    await service.add_admin(payload.persona_id, server.server_id)
    return AdminActionResult(success=True, message=f"已添加管理员 {payload.persona_id}")


@router.delete("/{game_id}/admin/{persona_id}", response_model=AdminActionResult)
async def remove_admin(
    game_id: int,
    persona_id: int,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    server = await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="owner")
    service = _admin_service(db, request, user, game_id)
    await service.remove_admin(persona_id, server.server_id)
    return AdminActionResult(success=True, message=f"已移除管理员 {persona_id}")


@router.post("/{game_id}/level", response_model=AdminActionResult)
async def choose_level(
    game_id: int,
    payload: ChooseLevelRequest,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    server = await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="admin")
    # 换图目标以授权服务器自身记录的 persisted_game_id 为准，不接受请求体传入值，
    # 与 ban/vip/admin 一致地只信任服务端可信标识，避免借他服 guid 越权换图。
    # 服务器尚未被 serverInfo 回填（persisted_game_id 为空）时无法换图，fail-closed 拒绝。
    if server.persisted_game_id is None:
        raise ForbiddenError(message="服务器尚未完成初始化，无法执行换图操作")
    service = _admin_service(db, request, user, game_id)
    await service.choose_level(server.persisted_game_id, payload.level_index)
    return AdminActionResult(
        success=True,
        message=f"已切换到地图序号 {payload.level_index}",
    )
