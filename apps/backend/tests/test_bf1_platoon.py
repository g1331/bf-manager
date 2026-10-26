"""战队详情：EA 三个返回拼装成详情"""

from __future__ import annotations

import pytest
from app.api.errors import NotFoundError
from app.services.bf1.platoon_service import build_detail, get_platoon_detail

INFO = {
    "result": {
        "guid": "66485c9e-01a9-4aeb-a30d-f02488fa357c",
        "name": "Electronic Arts",
        "size": 68,
        "joinConfig": {"canApplyMembership": True, "isFreeJoin": False},
        "description": "Employees of Electronic Arts - Invite Only.",
        "tag": "EA",
        "emblem": "https://eaassets-a.akamaihd.net/battlelog/bf-emblems/prod_default/exclusive/[SIZE]/EA.[FORMAT]",
        "verified": True,
        "creatorId": "173507079",
        "dateCreated": 1490805628,
    }
}


def _m(pid: str, role: str, name: str) -> dict:
    return {"personaId": pid, "platformId": "1", "role": role, "displayName": name, "avatar": ""}


def test_build_detail_sorts_members_by_role_and_keeps_servers() -> None:
    members = {
        "result": [
            _m("3", "role0", "zed"),
            _m("1", "role9", "boss"),
            _m("4", "role0", "Amy"),
            _m("2", "role6", "col"),
            _m("5", "role7", "odd"),
            {"personaId": None},
        ]
    }
    servers = {
        "result": [
            {
                "server": {
                    "gameId": "8623425550964",
                    "name": "[op]Operation",
                    "mapName": "MP_Forest",
                },
                "platoon": {"displayMembers": [_m("1", "role-2", "boss")]},
            },
            {"server": {}},
        ]
    }
    d = build_detail(INFO, members, servers)
    assert d.guid == "66485c9e-01a9-4aeb-a30d-f02488fa357c"
    assert d.created_at == 1490805628 and d.can_apply and not d.free_join
    assert "[SIZE]" not in (d.emblem_url or "")
    assert [(m.persona_id, m.role) for m in d.members] == [
        (1, "general"),
        (2, "colonel"),
        (4, "private"),
        (3, "private"),
        (5, None),
    ]
    assert len(d.servers) == 1
    assert d.servers[0].server.game_id == 8623425550964
    assert [(m.persona_id, m.role) for m in d.servers[0].members] == [(1, None)]


def test_build_detail_tolerates_member_and_server_failures() -> None:
    d = build_detail(INFO, "EA API请求时发生未知错误", "超时")
    assert d.name == "Electronic Arts" and d.members == [] and d.servers == []


async def test_invalid_guid_is_not_found_without_calling_ea() -> None:
    with pytest.raises(NotFoundError):
        await get_platoon_detail(None, "not-a-guid")  # type: ignore[arg-type]
