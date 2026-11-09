"""BF6 玩家路由"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import SessionFactoryDep
from app.api.errors import ValidationError
from app.api.rate_limit import rate_limit
from app.domain.games.bf6.resolver import normalize_name
from app.schemas.bf6.matches import Bf6MatchList
from app.schemas.bf6.player import Bf6PlatformParam, Bf6PlayerStats, Bf6ResolvedPlayer
from app.services.bf6 import match_service, player_service, presentation

router = APIRouter()

# 都会打到 EA，和 BF1 查人共用 lookup 限流桶与公共预算
_lookup = rate_limit("lookup")
# 只读库
_read = rate_limit("read")


@router.get("/resolve", dependencies=[_lookup], response_model=Bf6ResolvedPlayer)
async def resolve_player(
    name: str = Query(..., min_length=1, max_length=64, description="EA 账号显示名"),
    platform: Bf6PlatformParam | None = Query(None, description="只在该平台的账号里找"),
) -> Bf6ResolvedPlayer:
    if not normalize_name(name):
        raise ValidationError("name 不能为空")
    return await player_service.resolve_player(name, platform)


@router.get("/{nucleus_id}/stats", dependencies=[_lookup], response_model=Bf6PlayerStats)
async def get_player_stats(nucleus_id: int, session_factory: SessionFactoryDep) -> Bf6PlayerStats:
    if nucleus_id <= 0:
        raise ValidationError("nucleus_id 无效")
    return presentation.player_stats(
        await player_service.get_player_stats(session_factory, nucleus_id)
    )


@router.get("/{nucleus_id}/matches", dependencies=[_read], response_model=Bf6MatchList)
async def list_match_estimates(nucleus_id: int, session_factory: SessionFactoryDep) -> Bf6MatchList:
    """最近的对局估算。只读已记下的数据，不向 EA 请求；有人查过战绩后才开始记录。"""
    if nucleus_id <= 0:
        raise ValidationError("nucleus_id 无效")
    return presentation.matches(await match_service.list_estimates(session_factory, nucleus_id))
