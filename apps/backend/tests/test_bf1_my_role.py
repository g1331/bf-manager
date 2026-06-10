"""BF1 my-role 端点：返回当前登录用户对服务器的角色。

仅需登录、不要求任何角色。覆盖三种来源：平台 admin 旁路、登录用户无成员记录、
登录用户具体成员角色。前端据此 gating 内联服管入口。
"""

from __future__ import annotations

from app.models import Server, ServerMembership

SERVER_ID = 8901234567890
MY_ROLE_URL = f"/api/v1/bf1/server-admin/{SERVER_ID}/my-role"


async def test_my_role_platform_admin_bypasses(admin_client) -> None:
    client, _ = admin_client
    resp = await client.get(MY_ROLE_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_platform_admin"] is True
    assert body["role"] is None


async def test_my_role_user_without_membership(user_client) -> None:
    client, _ = user_client
    # 普通用户、且服务器尚未登记或无成员记录：无任何服管权限
    resp = await client.get(MY_ROLE_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_platform_admin"] is False
    assert body["role"] is None


async def test_my_role_user_with_membership(user_client, test_session) -> None:
    client, user = user_client
    server = Server(game="bf1", server_id=SERVER_ID)
    test_session.add(server)
    await test_session.flush()
    test_session.add(ServerMembership(user_id=user.id, server_pk=server.id, role="moderator"))
    await test_session.commit()

    resp = await client.get(MY_ROLE_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_platform_admin"] is False
    assert body["role"] == "moderator"
