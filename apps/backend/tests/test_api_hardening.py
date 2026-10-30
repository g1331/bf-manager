"""接口对外暴露面：生产不公开接口文档，公开接口都要挂限流。"""

from __future__ import annotations

from typing import Any

from app.api.deps import get_current_user, get_current_user_any_status
from app.api.v1 import auth, games, health
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.main import create_app
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

# 不需要通用限流的公开接口：
# - healthz、games 不碰 EA 也不读业务数据
# - session 只解当前 cookie，每个页面都会调
# - local-login、email-login、cancel-deletion 有按账号和 IP 的失败锁定（login_throttle），
#   比固定窗口更合适
_EXEMPT = {
    health.healthz,
    games.get_games,
    auth.session,
    auth.local_login,
    auth.email_login,
    auth.cancel_deletion,
}


def _api_routes(routes: list[Any]) -> list[APIRoute]:
    """展开 include_router 嵌套。新版 FastAPI 不再把子路由摊平到父路由的 routes 里。"""
    found = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif (child := getattr(route, "original_router", None)) is not None:
            found.extend(_api_routes(child.routes))
    return found


def _calls(dependant: Dependant) -> list[Any]:
    found = []
    for dep in dependant.dependencies:
        found.append(dep.call)
        found.extend(_calls(dep))
    return found


def _is_rate_limited(call: Any) -> bool:
    return getattr(call, "__qualname__", "").startswith("rate_limit.")


async def test_docs_hidden_in_production(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "environment", "production")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for path in ("/api/v1/openapi.json", "/docs", "/redoc"):
            assert (await c.get(path)).status_code == 404, path


async def test_docs_available_outside_production() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/api/v1/openapi.json")).status_code == 200


def test_every_anonymous_route_is_rate_limited() -> None:
    """不要求登录的接口都得挂限流；新增公开接口忘了加，这里会报出来。"""
    routes = _api_routes(api_router.routes)
    assert len(routes) > 50  # 确认真的展开了子路由，避免空遍历让测试形同虚设
    missing = []
    for route in routes:
        if route.endpoint in _EXEMPT:
            continue
        calls = _calls(route.dependant)
        if (
            get_current_user in calls
            or get_current_user_any_status in calls
            or any(_is_rate_limited(c) for c in calls)
        ):
            continue
        missing.append(f"{sorted(route.methods)} {route.path}")
    assert missing == []


async def test_public_openapi_only_lists_open_queries(monkeypatch) -> None:
    """生产也提供精简文档，只含 BF1 只读查询，不带管理接口和它们的 schema。"""
    monkeypatch.setattr(get_settings(), "environment", "production")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/openapi.public.json")
    assert resp.status_code == 200
    doc = resp.json()
    paths = doc["paths"]
    assert "/api/v1/bf1/stats/{persona_id}" in paths
    assert all(p.startswith("/api/v1/bf1/") for p in paths)
    assert not any("server-admin" in p or "/card" in p for p in paths)
    assert all(list(ops) == ["get"] for ops in paths.values())
    schemas = doc["components"]["schemas"]
    assert "PlayerStatsDetail" in schemas
    assert not any("EAAccount" in s or "Membership" in s for s in schemas)
    assert doc["components"]["securitySchemes"]["ApiKey"]["name"] == "X-API-Key"
