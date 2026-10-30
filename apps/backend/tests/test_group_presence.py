"""群成员在玩状态：名单倒排缓存的编解码、/groups/presence 接口"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.v1 import groups as groups_api
from app.schemas.bf1.server import ServerSummary
from app.services.bf1.presence_cache import decode_entry, encode_rosters
from app.services.bf1.server_roster_service import QUEUE, SPECTATOR, TEAM1, TEAM2

from tests.test_accounts import _login_cookie
from tests.test_groups import _invite_as, _join, _setup

API = "/api/v1"


def test_encode_and_decode_rosters() -> None:
    rosters = {
        10: {1: (TEAM1, "a"), 2: (QUEUE, "b")},
        20: {3: (SPECTATOR, "c"), 4: (TEAM2, "d")},
    }
    mapping = encode_rosters(rosters)
    assert mapping == {"1": "10:1", "2": "10:3", "3": "20:4", "4": "20:2"}
    assert decode_entry(mapping["1"]) == (10, "team1")
    assert decode_entry(mapping["2"]) == (10, "queue")
    assert decode_entry(mapping["3"]) == (20, "spectator")
    assert decode_entry(None) is None
    assert decode_entry("bad") is None
    # 位置 0 是 LEFT（已离开），不算在服
    assert decode_entry("10:0") is None


async def test_presence_lists_other_members_in_server_first(env, test_session, monkeypatch) -> None:
    ac, _, owner, alice, bob, gid = await _setup(env, test_session)
    await _join(ac, alice, await _invite_as(ac, owner, gid, "admin"))
    await _join(ac, bob, await _invite_as(ac, owner, gid, "admin"))

    ts = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    asked: list[list[int]] = []

    async def fake_presence(pids):
        asked.append(pids)
        return ts, {2003: (77, "team2")}

    async def fake_snapshot():
        return [
            ServerSummary(
                server_id=5,
                game_id=77,
                name="测试服",
                map_display_name="亚眠",
                mode_display_name="征服",
                player_count=60,
                max_player_count=64,
            )
        ]

    monkeypatch.setattr(groups_api, "read_presence", fake_presence)
    monkeypatch.setattr(groups_api, "read_server_snapshot", fake_snapshot)

    _login_cookie(ac, owner)
    resp = await ac.get(f"{API}/groups/presence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 自己不在列表里，也不去查自己
    assert asked == [[2002, 2003]]
    assert body["updated_at"].startswith("2026-10-30T12:00:00")
    (group,) = body["groups"]
    assert group["id"] == gid
    assert [m["persona_id"] for m in group["members"]] == [2003, 2002]
    assert group["members"][0]["server"] == {
        "game_id": 77,
        "slot": "team2",
        "name": "测试服",
        "map_display_name": "亚眠",
        "mode_display_name": "征服",
        "player_count": 60,
        "max_player_count": 64,
    }
    assert group["members"][1]["server"] is None


async def test_presence_unavailable_and_server_missing_from_snapshot(
    env, test_session, monkeypatch
) -> None:
    ac, _, owner, alice, _bob, gid = await _setup(env, test_session)
    await _join(ac, alice, await _invite_as(ac, owner, gid, "admin"))

    async def no_snapshot():
        return None

    async def unavailable(_pids):
        return None, {}

    monkeypatch.setattr(groups_api, "read_server_snapshot", no_snapshot)
    monkeypatch.setattr(groups_api, "read_presence", unavailable)
    _login_cookie(ac, alice)
    body = (await ac.get(f"{API}/groups/presence")).json()
    assert body["updated_at"] is None
    assert body["groups"][0]["members"][0]["server"] is None

    async def in_unknown_server(_pids):
        return datetime.now(UTC), {2001: (99, "queue")}

    monkeypatch.setattr(groups_api, "read_presence", in_unknown_server)
    member = (await ac.get(f"{API}/groups/presence")).json()["groups"][0]["members"][0]
    # 摘要缓存里没有这台服：只给 game_id 和位置，前端照样能跳到服务器页
    assert member["server"]["game_id"] == 99
    assert member["server"]["slot"] == "queue"
    assert member["server"]["name"] is None


async def test_presence_without_groups(env, test_session, monkeypatch) -> None:
    ac, _, _owner, alice, _bob, _gid = await _setup(env, test_session)

    async def fail():
        raise AssertionError("没人在服时不该读服务器摘要")

    async def empty(_pids):
        return None, {}

    monkeypatch.setattr(groups_api, "read_presence", empty)
    monkeypatch.setattr(groups_api, "read_server_snapshot", fail)
    _login_cookie(ac, alice)
    body = (await ac.get(f"{API}/groups/presence")).json()
    assert body == {"updated_at": None, "groups": []}
