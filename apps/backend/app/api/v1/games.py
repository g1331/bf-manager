"""游戏列表 API"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.game import GameInfo
from app.services.game_service import list_enabled_games

router = APIRouter()


@router.get("", response_model=list[GameInfo])
async def get_games() -> list[GameInfo]:
    return list_enabled_games()
