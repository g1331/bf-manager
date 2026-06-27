"""服务器鉴权：按 EA 服主 / 管理员名单自动识别角色

回归保护：服管 UI 与端点鉴权要求用户对该服有角色。改为「绑定 persona 命中 EA 侧 owner/
adminList 即授权」后，须保证：命中 owner→owner、命中 admin→admin、未命中→无角色，且识别成功
时以稳定 server_id 落库 Server（含末次 game_id）+ 自动 membership，供「我的服务器」枚举。

EA 调用（BF1ServerService.get_admin_identity）一律 monkeypatch，不发真实请求。
"""

from __future__ import annotations

from app.models import Server, ServerMembership
from app.services.authz_service import ServerAuthzService
from app.services.bf1 import server_service as ss_module
from sqlalchemy import select

GAME_ID = 555  # URL 寻址用的 EA gameId（易变）
SERVER_ID = 9001  # 稳定 EA serverId


def _patch_identity(monkeypatch, *, owner_pid, admin_pids, server_id=SERVER_ID, name="My Server"):
    async def fake_identity(self, game_id):
        return owner_pid, list(admin_pids), server_id, name

    monkeypatch.setattr(ss_module.BF1ServerService, "get_admin_identity", fake_identity)


async def test_owner_match_grants_owner_and_persists(user_client, test_session, monkeypatch):
    _, user = user_client
    pid = user.ea_bindings[0].persona_id
    _patch_identity(monkeypatch, owner_pid=pid, admin_pids=[])

    role, is_platform_admin = await ServerAuthzService(test_session).resolve_role(
        user=user, game="bf1", server_id=GAME_ID
    )
    assert (role, is_platform_admin) == ("owner", False)

    # Server 以稳定 server_id 落库，回填末次 game_id 与名称
    server = await test_session.scalar(select(Server).where(Server.server_id == SERVER_ID))
    assert server is not None
    assert server.game_id == GAME_ID
    assert server.name == "My Server"

    # 自动 membership（granted_by 为空）
    membership = await test_session.scalar(
        select(ServerMembership).where(ServerMembership.server_pk == server.id)
    )
    assert membership is not None
    assert membership.role == "owner"
    assert membership.granted_by is None


async def test_admin_list_match_grants_admin(user_client, test_session, monkeypatch):
    _, user = user_client
    pid = user.ea_bindings[0].persona_id
    _patch_identity(monkeypatch, owner_pid=999, admin_pids=[pid])

    role, _ = await ServerAuthzService(test_session).resolve_role(
        user=user, game="bf1", server_id=GAME_ID
    )
    assert role == "admin"


async def test_no_match_no_role_and_no_membership(user_client, test_session, monkeypatch):
    _, user = user_client
    _patch_identity(monkeypatch, owner_pid=999, admin_pids=[888])

    role, is_platform_admin = await ServerAuthzService(test_session).resolve_role(
        user=user, game="bf1", server_id=GAME_ID
    )
    assert (role, is_platform_admin) == (None, False)
    # 不命中者不应落任何自动 membership
    membership = await test_session.scalar(select(ServerMembership))
    assert membership is None


async def test_platform_admin_bypasses_without_ea_call(admin_client, test_session, monkeypatch):
    _, admin = admin_client

    async def boom(self, game_id):
        raise AssertionError("平台 admin 不应触发 EA 识别")

    monkeypatch.setattr(ss_module.BF1ServerService, "get_admin_identity", boom)
    role, is_platform_admin = await ServerAuthzService(test_session).resolve_role(
        user=admin, game="bf1", server_id=GAME_ID
    )
    assert (role, is_platform_admin) == (None, True)


async def test_my_servers_endpoint_lists_recognized(user_client, test_session, monkeypatch):
    client, user = user_client
    pid = user.ea_bindings[0].persona_id
    _patch_identity(monkeypatch, owner_pid=pid, admin_pids=[])

    # 访问触发识别落库
    await ServerAuthzService(test_session).resolve_role(user=user, game="bf1", server_id=GAME_ID)

    resp = await client.get("/api/v1/bf1/server-admin/mine")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["server_id"] == SERVER_ID
    assert items[0]["game_id"] == GAME_ID
    assert items[0]["role"] == "owner"
