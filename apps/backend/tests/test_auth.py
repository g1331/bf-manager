"""认证端点轻量集成测试"""

from __future__ import annotations

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_session_without_cookie_returns_null_user() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json() == {"user": None}


@pytest.mark.asyncio
async def test_logout_without_session_returns_401() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_remid_login_is_gone() -> None:
    """remid 登录已下线，remid 只用来绑定 EA"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", json={"remid": "x" * 20, "sid": ""})
    assert resp.status_code in (404, 405)
