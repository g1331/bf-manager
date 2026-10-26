"""战队详情：EA 三个返回拼装成详情"""

from __future__ import annotations

import pytest
from app.api.errors import NotFoundError
from app.domain.games.bf1.maps import normalize_emblem_url
from app.services.bf1.platoon_service import build_detail, build_search, get_platoon_detail

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


def test_build_search_maps_fields_and_upgrades_http_emblem() -> None:
    res = {
        "result": [
            {
                "guid": "128f4998-63f2-43a4-a8b6-958e8f4ab6c4",
                "name": "Grumpy Old Warriors",
                "size": 2,
                "tag": "GOW",
                "emblem": "http://eaassets-a.akamaihd.net/battlelog/prod/emblem/693/916/[SIZE]/1.[FORMAT]?v=1",
                "verified": False,
                "displayMembers": [],
            },
            {"name": "no guid"},
        ]
    }
    items = build_search(res)
    assert [(i.guid, i.tag, i.size) for i in items] == [
        ("128f4998-63f2-43a4-a8b6-958e8f4ab6c4", "GOW", 2)
    ]
    assert items[0].emblem_url == (
        "https://eaassets-a.akamaihd.net/battlelog/prod/emblem/693/916/512/1.png?v=1"
    )
    assert build_search("戰隊名稱太短") == []
    assert normalize_emblem_url(None) is None
