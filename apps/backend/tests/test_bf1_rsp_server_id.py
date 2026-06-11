"""RSP 名单操作的 serverId 解析

RSP.addServerVip / removeServerBan 等名单操作要的是 rspInfo.server.serverId，
不是 URL 路径里的 gameId——两者都叫 server id 但语义不同，错传 gameId 时 EA 返回
InvalidServerIdException（2026-06-11 生产实测）。服务端在执行前按 game_id 调
getFullServerDetails 实时解析，本用例锁定解析来源与寻址入参。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from app.api.errors import EAApiError
from app.services.bf1.server_admin_service import BF1ServerAdminService

GAME_ID = 10970335350265
RSP_SERVER_ID = 12478776


class _FakeClient:
    """返回固定详情、记录名单操作入参的假客户端"""

    def __init__(self, sink: dict, detail: dict) -> None:
        self._sink = sink
        self._detail = detail

    async def getFullServerDetails(self, gameId):  # noqa: N802, N803 (对齐 gateway 签名)
        self._sink["detail_game_id"] = gameId
        return {"result": self._detail}

    def _record(self, method: str, personaId, serverId):  # noqa: N803
        self._sink[method] = (personaId, serverId)
        return {"ok": True}

    async def addServerVip(self, personaId, serverId):  # noqa: N802, N803
        return self._record("addServerVip", personaId, serverId)

    async def removeServerVip(self, personaId, serverId):  # noqa: N802, N803
        return self._record("removeServerVip", personaId, serverId)

    async def addServerBan(self, personaId, serverId):  # noqa: N802, N803
        return self._record("addServerBan", personaId, serverId)

    async def removeServerBan(self, personaId, serverId):  # noqa: N802, N803
        return self._record("removeServerBan", personaId, serverId)

    async def addServerAdmin(self, personaId, serverId):  # noqa: N802, N803
        return self._record("addServerAdmin", personaId, serverId)

    async def removeServerAdmin(self, personaId, serverId):  # noqa: N802, N803
        return self._record("removeServerAdmin", personaId, serverId)


class _FakeProvider:
    def __init__(self, sink: dict, detail: dict) -> None:
        self._sink = sink
        self._detail = detail

    @asynccontextmanager
    async def acquire(self):
        yield _FakeClient(self._sink, self._detail)


def _service(test_session, admin, sink: dict, detail: dict) -> BF1ServerAdminService:
    return BF1ServerAdminService(
        test_session,
        user=admin,
        game_id=GAME_ID,
        client_provider=_FakeProvider(sink, detail),
    )


async def test_member_ops_use_resolved_rsp_server_id(admin_client, test_session) -> None:
    _, admin = admin_client
    sink: dict = {}
    # EA 返回字符串形态的 serverId，解析后应转 int 并用于全部六个名单操作
    detail = {"rspInfo": {"server": {"serverId": str(RSP_SERVER_ID)}}}
    service = _service(test_session, admin, sink, detail)

    await service.add_vip(999)
    await service.remove_vip(999)
    await service.add_ban(999)
    await service.remove_ban(999)
    await service.add_admin(999)
    await service.remove_admin(999)

    # 详情解析按 URL 的 game_id 寻址，名单操作按解析出的 RSP serverId 寻址
    assert sink["detail_game_id"] == GAME_ID
    for method in (
        "addServerVip",
        "removeServerVip",
        "addServerBan",
        "removeServerBan",
        "addServerAdmin",
        "removeServerAdmin",
    ):
        assert sink[method] == (999, RSP_SERVER_ID)


async def test_member_op_fails_before_ea_when_rsp_server_id_missing(
    admin_client, test_session
) -> None:
    _, admin = admin_client
    sink: dict = {}
    # rspInfo 缺失（如后台账号拿不到 RSP 信息）：在触达名单操作前报错
    service = _service(test_session, admin, sink, {"serverInfo": {}})

    with pytest.raises(EAApiError) as exc_info:
        await service.remove_vip(999)

    assert exc_info.value.code == "EA_RSP_SERVER_ID_MISSING"
    assert "removeServerVip" not in sink
