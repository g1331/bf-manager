"""v1 路由聚合"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    audit,
    auth,
    ea_accounts,
    ea_login_tasks,
    games,
    health,
    me,
    memberships,
)
from app.api.v1.games import bf1 as bf1_routes

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit"])
api_router.include_router(memberships.router, prefix="/memberships", tags=["memberships"])
api_router.include_router(ea_accounts.router, prefix="/ea-accounts", tags=["ea-accounts"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
# EA 邮箱密码登录任务：user 与 admin 两组对称端点。前缀显式包含 ``login-tasks``，
# 避免被 ea_accounts.py 的 ``/{account_id}`` 动态路由吞掉。
api_router.include_router(
    ea_login_tasks.me_router,
    prefix="/me/ea-bindings/login-tasks",
    tags=["ea-login-tasks"],
)
api_router.include_router(
    ea_login_tasks.admin_router,
    prefix="/ea-accounts/login-tasks",
    tags=["ea-login-tasks"],
)
api_router.include_router(bf1_routes.router)
