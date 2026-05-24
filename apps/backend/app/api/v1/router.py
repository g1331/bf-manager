"""v1 路由聚合"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, games, health

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
