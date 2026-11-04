"""BF1 换边端点：teamId 映射方向 + min_role 门槛 + team_id 取值边界

换边复用 RSP.movePlayer，其 teamId 语义是玩家「当前源队伍号」（1-based）：传入源队伍号，
引擎把玩家移到对面。Blaze 名单的 team 是 0/1，故 rsp_team = team_id + 1。本用例锁定这个
映射方向（移错方向会把玩家换到错误阵营），并覆盖管理员门槛与 team_id 取值边界。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from app.services.bf1 import server_service as ss_module
from app.services.bf1.server_admin_service import BF1ServerAdminService

SERVER_ID = 8901234567890
MOVE_URL = f"/api/v1/bf1/server-admin/{SERVER_ID}/move"


class _CapturingClient:
    """记录 movePlayer 入参的假客户端，用于验证 teamId 映射"""

    def __init__(self, sink: dict) -> None:
        self._sink = sink

    async def movePlayer(self, gameId, personaId, teamId):  # noqa: N802, N803 (对齐 gateway 签名)
        self._sink["args"] = (gameId, personaId, teamId)
        return {"ok": True}


class _CapturingProvider:
    """符合 BF1ClientProvider 协议的假 provider，acquire 产出记录入参的假客户端"""

    def __init__(self, sink: dict) -> None:
        self._sink = sink

    @asynccontextmanager
    async def acquire(self):
        yield _CapturingClient(self._sink)


async def test_move_maps_blaze_team_to_rsp_source_team(admin_client, test_session) -> None:
    _, admin = admin_client
    sink: dict = {}
    service = BF1ServerAdminService(
        test_session, user=admin, game_id=123, client_provider=_CapturingProvider(sink)
    )

    # blaze team 0 → RSP 源队伍号 1（传源队伍号，引擎据此把玩家换到对面）
    await service.move_player(persona_id=999, team_id=0)
    assert sink["args"] == (123, 999, 1)

    # blaze team 1 → RSP 源队伍号 2
    await service.move_player(persona_id=999, team_id=1)
    assert sink["args"] == (123, 999, 2)


async def test_move_rejects_out_of_range_team(admin_client) -> None:
    client, _ = admin_client
    # team_id 只接受 0/1（玩家当前 blaze 队伍）；越界值在 Pydantic 解析阶段 422，不触达 EA
    resp = await client.post(MOVE_URL, json={"persona_id": 999, "team_id": 2})
    assert resp.status_code == 422


async def test_move_requires_server_role(user_client) -> None:
    client, _ = user_client
    # 没有任何服管角色 → 403，不触达 EA
    resp = await client.post(MOVE_URL, json={"persona_id": 999, "team_id": 0})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_server_admin_can_kick_and_move_but_not_manage_admins(
    user_client, monkeypatch
) -> None:
    """服管权限只有管理员、服主两级：管理员能踢人换边，增删游戏内管理员仍只给服主"""
    client, user = user_client
    pid = user.ea_bindings[0].persona_id

    async def fake_identity(self, game_id):
        return 999, [pid], 9001, "My Server"  # 用户在 EA 管理员名单里，不是服主

    monkeypatch.setattr(ss_module.BF1ServerService, "get_admin_identity", fake_identity)
    calls: list[str] = []

    async def fake_kick(self, persona_id, reason):
        calls.append("kick")

    async def fake_move(self, persona_id, team_id):
        calls.append("move")

    async def fake_add_admin(self, persona_id):
        calls.append("add_admin")

    monkeypatch.setattr(BF1ServerAdminService, "kick_player", fake_kick)
    monkeypatch.setattr(BF1ServerAdminService, "move_player", fake_move)
    monkeypatch.setattr(BF1ServerAdminService, "add_admin", fake_add_admin)

    base = f"/api/v1/bf1/server-admin/{SERVER_ID}"
    resp = await client.post(f"{base}/kick", json={"persona_id": 42})
    assert resp.status_code == 200, resp.text
    resp = await client.post(MOVE_URL, json={"persona_id": 42, "team_id": 0})
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"{base}/admin", json={"persona_id": 42})
    assert resp.status_code == 403
    assert calls == ["kick", "move"]
