"""服管权限授予路由：未登录 401 + 普通用户 403 + admin 增删查"""

from __future__ import annotations

from app.models import Server, User
from sqlalchemy import select


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

    target = User(
        id=42,
        persona_id=1003517866915,
        display_name="XMMXML",
        role="user",
        is_active=True,
    )
    test_session.add(target)
    await test_session.commit()

    payload = {
        "target_persona_id": target.persona_id,
        "game": "bf1",
        "server_id": 13110853,
        "role": "moderator",
    }

    resp = await ac.post("/api/v1/memberships", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_persona_id"] == target.persona_id
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
    target = User(id=2, persona_id=2, display_name="x", role="user", is_active=True)
    test_session.add(target)
    await test_session.commit()

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
