"""EA 上游失败的错误契约：状态码 503 + 错误文案穿透到响应体

生产外层的 Cloudflare 会把源站 502/504 响应整体替换为自家 HTML 错误页，JSON 错误体
到不了浏览器，前端只能展示空白报错（2026-06-10 生产封禁操作实测复现）。因此 EAApiError
必须映射为 503，且 EA 返回的错误文案要完整保留在 message 里供前端 toast 展示。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from app.api.errors import EAApiError
from app.services.bf1.server_admin_service import BF1ServerAdminService


class _FailingClient:
    """模拟 gateway 约定的失败形态：EA 调用失败时返回错误字符串而非 dict"""

    async def movePlayer(self, gameId, personaId, teamId):  # noqa: N802, N803 (对齐 gateway 签名)
        return "服务器管理员列表已满"


class _FailingProvider:
    @asynccontextmanager
    async def acquire(self):
        yield _FailingClient()


async def test_ea_error_maps_to_503_with_message(admin_client, test_session) -> None:
    _, admin = admin_client
    service = BF1ServerAdminService(
        test_session, user=admin, game_id=123, client_provider=_FailingProvider()
    )

    with pytest.raises(EAApiError) as exc_info:
        await service.move_player(persona_id=999, team_id=0)

    err = exc_info.value
    # 503 而非 502：502/504 会被 Cloudflare 吞掉响应体，浏览器拿不到 JSON 错误
    assert err.status_code == 503
    assert err.code == "EA_MOVE_FAILED"
    # EA 的错误文案必须原样进 message，前端 toast 直接展示给服管
    assert err.message == "服务器管理员列表已满"
