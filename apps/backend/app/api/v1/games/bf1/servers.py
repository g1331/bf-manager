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
    name: str | None = Query(None, max_length=64, description="按服务器名关键字过滤"),
    limit: int = Query(50, ge=1, le=200),
) -> ServerListResponse:
    return await BF1ServerService(db).search(keyword=name, limit=limit)


@router.get("/{game_id}", response_model=ServerDetail)
async def get_server(game_id: int, db: DbDep) -> ServerDetail:
    return await BF1ServerService(db).get_detail(game_id)
