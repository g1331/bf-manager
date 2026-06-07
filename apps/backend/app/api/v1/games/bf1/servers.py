"""BF1 服务器查询路由"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.schemas.bf1.server import ServerDetail, ServerListResponse
from app.services.bf1.server_service import BF1ServerService

router = APIRouter()


@router.get("", response_model=ServerListResponse)
async def list_servers(
    db: DbDep,
    name: str | None = Query(
        None, max_length=64, description="按服务器名关键字过滤（EA 端包含匹配，大小写不敏感）"
    ),
    maps: list[str] | None = Query(None, description="地图代号（MP_*），多值取并集"),
    modes: list[str] | None = Query(None, description="模式代号，多值取并集"),
    regions: list[str] | None = Query(None, description="地区代号，多值取并集"),
    sizes: list[int] | None = Query(None, description="服务器最大人数档位，多值取并集"),
    limit: int = Query(200, ge=1, le=500),
) -> ServerListResponse:
    # 筛选条件下推到 EA searchServers 按条件检索。空位（emptySlots）EA 不支持过滤，
    # 由前端二次过滤。EA searchServers 只接受 limit，没有 offset，前端走客户端分批渲染。
    return await BF1ServerService(db).search(
        keyword=name,
        maps=maps,
        modes=modes,
        regions=regions,
        sizes=sizes,
        limit=limit,
    )


@router.get("/{game_id}", response_model=ServerDetail)
async def get_server(game_id: int, db: DbDep) -> ServerDetail:
    return await BF1ServerService(db).get_detail(game_id)
