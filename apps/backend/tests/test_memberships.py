"""服管权限授予路由：未登录 401 + 普通用户 403 + admin 增删查"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import EaBinding, Server, User
from sqlalchemy import select


async def _create_target_user(session, *, user_id: int, persona_id: int, username: str) -> User:
    user = User(
        id=user_id,
        username=username,
        local_password_hash=None,
        email=None,
        role="user",
        is_active=True,
        is_frozen=False,
    )
    session.add(user)
    await session.flush()
    session.add(
        EaBinding(
            user_id=user.id,
            persona_id=persona_id,
            display_name=f"Target_{persona_id}",
            avatar_url=None,
            encrypted_remid=None,
            encrypted_sid=None,
            encrypted_session=None,
            encrypted_access_token=None,
            is_primary=True,
            is_frozen=False,
            last_verified_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return user


async def test_memberships_requires_login(client) -> None:
    resp = await client.get("/api/v1/memberships")
    assert resp.status_code == 401


async def test_memberships_user_forbidden(user_client) -> None:
    ac, _user = user_client
    resp = await ac.get("/api/v1/memberships")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_memberships_admin_empty_list(admin_client) -> None:
    ac, _admin = admin_client
    resp = await ac.get("/api/v1/memberships")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_memberships_admin_upsert_and_delete(admin_client, test_session) -> None:
    ac, _admin = admin_client

    target = await _create_target_user(
        test_session, user_id=42, persona_id=1003517866915, username="persona_1003517866915"
    )

    payload = {
        "target_persona_id": 1003517866915,
        "game": "bf1",
        "server_id": 13110853,
        "role": "moderator",
    }

    resp = await ac.post("/api/v1/memberships", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_persona_id"] == 1003517866915
    assert body["user_username"] == target.username
    assert body["role"] == "moderator"
    membership_id = body["id"]

    # 重复 upsert 应覆盖角色
    payload["role"] = "admin"
    resp = await ac.post("/api/v1/memberships", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == membership_id
    assert body["role"] == "admin"

    resp = await ac.get("/api/v1/memberships")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = await ac.delete(f"/api/v1/memberships/{membership_id}")
    assert resp.status_code == 204

    resp = await ac.get("/api/v1/memberships")
    assert resp.json()["total"] == 0


async def test_memberships_upsert_unknown_user_returns_404(admin_client) -> None:
    ac, _admin = admin_client
    resp = await ac.post(
        "/api/v1/memberships",
        json={
            "target_persona_id": 99999999,
            "game": "bf1",
            "server_id": 1,
            "role": "viewer",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_memberships_creates_server_record_on_first_upsert(
    admin_client, test_session
) -> None:
    """upsert 时若 (game, server_id) 对应的 Server 不存在，应自动注册一条"""
    ac, _admin = admin_client
    await _create_target_user(test_session, user_id=2, persona_id=2, username="persona_2")

    resp = await ac.post(
        "/api/v1/memberships",
        json={
            "target_persona_id": 2,
            "game": "bf1",
            "server_id": 999,
            "role": "owner",
        },
    )
    assert resp.status_code == 200

    server = await test_session.scalar(
        select(Server).where(Server.game == "bf1", Server.server_id == 999)
    )
    assert server is not None
