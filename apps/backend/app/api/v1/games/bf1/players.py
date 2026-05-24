"""BF1 玩家路由"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.api.errors import ValidationError
from app.schemas.bf1.player import PersonaBrief, PersonaSearchResult
from app.services.bf1.player_service import BF1PlayerService

router = APIRouter()


@router.get("/search", response_model=PersonaSearchResult)
async def search_players(
    db: DbDep,
    name: str = Query(..., min_length=2, max_length=64, description="EA 昵称（区分大小写）"),
) -> PersonaSearchResult:
    if not name.strip():
        raise ValidationError("name 不能为空")
    return await BF1PlayerService(db).search_by_name(name.strip())


@router.get("/{persona_id}", response_model=PersonaBrief)
async def get_player(persona_id: int, db: DbDep) -> PersonaBrief:
    return await BF1PlayerService(db).get_by_id(persona_id)
