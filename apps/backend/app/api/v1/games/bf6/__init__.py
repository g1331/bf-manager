"""BF6 路由聚合"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.games.bf6 import players

router = APIRouter(prefix="/bf6", tags=["bf6"])
router.include_router(players.router, prefix="/players")
