"""/auth/session 与 is_frozen 拒绝登录的回归测试"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.passwords import hash_password
from app.core.security import create_access_token, decode_access_token
from app.models import User
from jose import jwt


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


async def test_local_login_rejects_frozen_admin(client, test_session) -> None:
    """is_frozen=true 的本地 admin 走 local-login 应被 401 拒绝，
    避免颁发出来的 JWT 在后续请求被 get_current_user 拒绝、前端陷入死循环"""
    admin = User(
        id=201,
        username="frozen_admin",
        local_password_hash=hash_password("correct-pw"),
        email=None,
        role="admin",
        is_active=True,
        is_frozen=True,
    )
    test_session.add(admin)
    await test_session.commit()

    resp = await client.post(
        "/api/v1/auth/local-login",
        json={"username": "frozen_admin", "password": "correct-pw"},
    )
    assert resp.status_code == 401
    # 不应携带 set-cookie
    assert "bfm_access_token" not in resp.cookies


def _token_issued_at(user_id: int, issued_at: datetime) -> str:
    """签发一张指定签发时间的会话 token，模拟登录了一段时间的用户。"""
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(days=30)).timestamp()),
        "type": "access",
        "role": "user",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def _add_active_user(test_session, user_id: int) -> User:
    user = User(
        id=user_id,
        username=f"active_{user_id}",
        local_password_hash=None,
        email=None,
        role="user",
        is_active=True,
        is_frozen=False,
    )
    test_session.add(user)
    await test_session.commit()
    return user


async def test_session_renews_token_issued_over_a_day_ago(client, test_session) -> None:
    """token 签发超过 24 小时，/session 换发新 token，有效期重新算满"""
    user = await _add_active_user(test_session, 210)
    client.cookies.set(
        "bfm_access_token", _token_issued_at(user.id, datetime.now(UTC) - timedelta(days=2))
    )

    resp = await client.get("/api/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == user.id

    renewed = resp.cookies.get("bfm_access_token")
    assert renewed is not None
    payload = decode_access_token(renewed)
    assert payload["sub"] == str(user.id)
    expected_exp = datetime.now(UTC) + timedelta(
        minutes=get_settings().jwt_access_token_expire_minutes
    )
    assert abs(payload["exp"] - expected_exp.timestamp()) < 60


async def test_session_keeps_fresh_token(client, test_session) -> None:
    """token 签发不到 24 小时，/session 不重写 cookie"""
    user = await _add_active_user(test_session, 211)
    client.cookies.set(
        "bfm_access_token", _token_issued_at(user.id, datetime.now(UTC) - timedelta(hours=1))
    )

    resp = await client.get("/api/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == user.id
    assert "set-cookie" not in resp.headers


async def test_session_anonymous_sets_no_cookie(client) -> None:
    """未登录访问 /session 不签发任何 cookie"""
    resp = await client.get("/api/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json()["user"] is None
    assert "set-cookie" not in resp.headers
