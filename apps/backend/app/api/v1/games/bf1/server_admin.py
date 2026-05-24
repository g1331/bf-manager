"""BF1 服管操作路由（需登录 + 服务器权限）"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbDep
from app.schemas.bf1.admin import (
    AdminActionResult,
    BanPlayerRequest,
    ChooseLevelRequest,
    KickPlayerRequest,
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


@router.post("/{game_id}/level", response_model=AdminActionResult)
async def choose_level(
    game_id: int,
    payload: ChooseLevelRequest,
    db: DbDep,
    user: CurrentUser,
    request: Request,
) -> AdminActionResult:
    authz = ServerAuthzService(db)
    await authz.require_role(user=user, game="bf1", server_id=game_id, min_role="admin")
    service = _admin_service(db, request, user, game_id)
    await service.choose_level(payload.persisted_game_id, payload.level_index)
    return AdminActionResult(
        success=True,
        message=f"已切换到地图序号 {payload.level_index}",
    )
