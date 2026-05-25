"""/auth/session 与 is_frozen 拒绝登录的回归测试"""

from __future__ import annotations

from app.core.security import create_access_token
from app.models import User


async def test_session_returns_local_admin_without_binding(local_admin_client) -> None:
    """本地 admin 无任何 ea_binding 时，session 应正常返回，primary_binding 为 null"""
    ac, admin = local_admin_client
    resp = await ac.get("/api/v1/auth/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == admin.id
    assert body["user"]["username"] == "root"
    assert body["user"]["role"] == "admin"
    assert body["user"]["primary_binding"] is None


async def test_session_returns_ea_user_with_primary_binding(user_client) -> None:
    """EA 登录用户的 session 应携带 primary_binding 摘要"""
    ac, _user = user_client
    resp = await ac.get("/api/v1/auth/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == "persona_1003517866915"
    pb = body["user"]["primary_binding"]
    assert pb is not None
    assert pb["persona_id"] == 1003517866915
    assert pb["is_primary"] is True
    assert pb["is_frozen"] is False


async def test_frozen_user_cannot_use_session(client, test_session) -> None:
    """user.is_frozen=true 的账号不能通过 get_current_user，所有需鉴权接口返回 401"""
    user = User(
        id=200,
        username="banned_admin",
        local_password_hash=None,
        email=None,
        role="user",
        is_active=True,
        is_frozen=True,
    )
    test_session.add(user)
    await test_session.commit()

    token = create_access_token(subject=user.id, extra_claims={"role": user.role})
    ac = client
    ac.cookies.set("bfm_access_token", token)

    # /session 是可选鉴权：内部 get_current_user_optional 捕获 UnauthorizedError 返回 None
    resp = await ac.get("/api/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json()["user"] is None

    # /memberships 是强制鉴权：被 is_frozen 卡掉返回 401
    resp = await ac.get("/api/v1/memberships")
    assert resp.status_code == 401
