"""BF1 路由聚合"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.games.bf1 import players, server_admin, servers, stats

router = APIRouter(prefix="/bf1", tags=["bf1"])
router.include_router(players.router, prefix="/players")
router.include_router(stats.router, prefix="/stats")
router.include_router(servers.router, prefix="/servers")
router.include_router(server_admin.router, prefix="/server-admin")
