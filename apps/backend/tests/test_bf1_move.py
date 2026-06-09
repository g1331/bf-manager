"""BF1 换边端点：teamId 映射方向 + min_role 门槛 + team_id 取值边界

换边复用 RSP.movePlayer，其 teamId 语义是玩家「当前源队伍号」（1-based）：传入源队伍号，
引擎把玩家移到对面。Blaze 名单的 team 是 0/1，故 rsp_team = team_id + 1。本用例锁定这个
映射方向（移错方向会把玩家换到错误阵营），并覆盖 moderator 门槛与 team_id 取值边界。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from app.models import Server, ServerMembership
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


async def test_move_requires_moderator(user_client, test_session) -> None:
    client, user = user_client
    # 建服务器并只给 viewer 成员角色：换边要求 moderator 及以上 → 403
    server = Server(game="bf1", server_id=SERVER_ID)
    test_session.add(server)
    await test_session.flush()
    test_session.add(ServerMembership(user_id=user.id, server_pk=server.id, role="viewer"))
    await test_session.commit()

    resp = await client.post(MOVE_URL, json={"persona_id": 999, "team_id": 0})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
