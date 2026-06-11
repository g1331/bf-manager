"""BF1 换图目标解析与 fail-closed 行为

换图目标不接受请求体传入，由服务端按 game_id 调 getFullServerDetails 实时解析
persistedGameId。覆盖三点：EA 详情缺 persistedGameId 时在触达 chooseLevel 前
fail-closed 拒绝；解析成功时以解析值寻址；请求体即便夹带 persisted_game_id 也被
schema 丢弃（横向越权结构性消除）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from app.api.errors import ForbiddenError
from app.schemas.bf1.admin import ChooseLevelRequest
from app.services.bf1.server_admin_service import BF1ServerAdminService


class _FakeClient:
    """返回固定详情、记录 chooseLevel 入参的假客户端"""

    def __init__(self, sink: dict, detail: dict) -> None:
        self._sink = sink
        self._detail = detail

    async def getFullServerDetails(self, gameId):  # noqa: N802, N803 (对齐 gateway 签名)
        return {"result": self._detail}

    async def chooseLevel(self, persistedGameId, levelIndex):  # noqa: N802, N803
        self._sink["args"] = (persistedGameId, levelIndex)
        return {"ok": True}


class _FakeProvider:
    def __init__(self, sink: dict, detail: dict) -> None:
        self._sink = sink
        self._detail = detail

    @asynccontextmanager
    async def acquire(self):
        yield _FakeClient(self._sink, self._detail)


async def test_choose_level_fails_closed_when_persisted_game_id_missing(
    admin_client, test_session
) -> None:
    _, admin = admin_client
    sink: dict = {}
    # EA 详情没有 persistedGameId（服务器未完成初始化）：fail-closed 拒绝，
    # 不触达 chooseLevel。
    service = BF1ServerAdminService(
        test_session,
        user=admin,
        game_id=123,
        client_provider=_FakeProvider(sink, {"serverInfo": {}}),
    )

    with pytest.raises(ForbiddenError):
        await service.choose_level(level_index=3)
    assert "args" not in sink


async def test_choose_level_uses_resolved_persisted_game_id(admin_client, test_session) -> None:
    _, admin = admin_client
    sink: dict = {}
    service = BF1ServerAdminService(
        test_session,
        user=admin,
        game_id=123,
        client_provider=_FakeProvider(sink, {"serverInfo": {"persistedGameId": "guid-1"}}),
    )

    await service.choose_level(level_index=3)
    assert sink["args"] == ("guid-1", 3)


def test_choose_level_schema_drops_client_supplied_persisted_game_id() -> None:
    # 请求体夹带任意 persisted_game_id（旧客户端或越权尝试）：schema 无该字段，
    # Pydantic 静默丢弃，换图目标只可能来自服务端解析。
    req = ChooseLevelRequest.model_validate(
        {"level_index": 3, "persisted_game_id": "attacker-controlled-guid"}
    )
    assert not hasattr(req, "persisted_game_id")
