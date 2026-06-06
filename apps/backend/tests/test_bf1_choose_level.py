"""BF1 换图端点的授权派生与 fail-closed 行为

换图目标不再接受请求体传入，由后端依授权服务器自身记录的 persisted_game_id 派生。
覆盖两点：服务器尚未回填 persisted_game_id 时在触达 EA 网关前 fail-closed 拒绝；
请求体即便夹带 persisted_game_id 也被忽略，不影响结果（横向越权已结构性消除）。
"""

from __future__ import annotations

LEVEL_URL = "/api/v1/bf1/server-admin/8901234567890/level"


async def test_choose_level_fails_closed_when_server_not_synced(admin_client) -> None:
    client, _ = admin_client
    # 平台管理员对一个尚未被 serverInfo 回填 persisted_game_id 的服务器换图：
    # require_role 旁路新建的服务器记录 persisted_game_id 为空，守卫据此 403，
    # 不会触达 EA 网关。
    resp = await client.post(LEVEL_URL, json={"level_index": 3})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_choose_level_ignores_client_supplied_persisted_game_id(admin_client) -> None:
    client, _ = admin_client
    # 请求体夹带任意 persisted_game_id（旧客户端或越权尝试）：schema 已移除该字段，
    # Pydantic 静默丢弃，换图目标仍只依授权服务器记录派生，因此结果与不传时一致
    # （此处服务器未同步，仍 403），证明客户端传值对换图目标无任何影响。
    resp = await client.post(
        LEVEL_URL,
        json={"level_index": 3, "persisted_game_id": "attacker-controlled-guid"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
