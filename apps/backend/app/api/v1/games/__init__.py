"""游戏相关路由聚合

- /api/v1/games          通用游戏列表
- /api/v1/bf1/...        BF1 特定路由（players / stats / servers / ...）
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.game import GameInfo
from app.services.game_service import list_enabled_games

router = APIRouter()


@router.get("", response_model=list[GameInfo])
async def get_games() -> list[GameInfo]:
    return list_enabled_games()
