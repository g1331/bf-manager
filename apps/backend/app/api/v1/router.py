"""v1 路由聚合"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import audit, auth, ea_accounts, games, health, me, memberships
from app.api.v1.games import bf1 as bf1_routes

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit"])
api_router.include_router(memberships.router, prefix="/memberships", tags=["memberships"])
api_router.include_router(ea_accounts.router, prefix="/ea-accounts", tags=["ea-accounts"])
api_router.include_router(bf1_routes.router)
