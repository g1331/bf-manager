"""私服名单的存取、轮流刷新、过期清理，以及按玩家反查（天眼查）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api.errors import EAApiError
from app.models.bf1.rsp_lists import Bf1RspMember, Bf1RspServer
from app.schemas.bf1.server import ServerExtras, ServerMember, ServerOwner, ServerSummary
from app.services.bf1 import rsp_list_service
from app.services.bf1.rsp_list_service import (
    list_player_servers,
    refresh_stale_lists,
    remember_detail_lists,
    store_lists,
)
from app.services.bf1.server_service import BF1ServerService
from sqlalchemy import select


def _extras(sid: int, *, owner: int = 1, admins=(), vips=(), bans=()) -> ServerExtras:
    def members(pids) -> list[ServerMember]:
        return [ServerMember(persona_id=p, display_name=f"p{p}") for p in pids]

    return ServerExtras(
        server_id=sid,
        owner=ServerOwner(persona_id=owner, display_name=f"p{owner}"),
        admins=members(admins),
        vips=members(vips),
        banned=members(bans),
    )


def _s(gid: int, name: str, players: int = 10) -> ServerSummary:
    return ServerSummary(
        server_id=0, game_id=gid, name=name, player_count=players, max_player_count=64
    )


async def _no_snapshot():
    return None


async def test_store_replaces_lists_and_lookup_groups_by_role(test_session, monkeypatch) -> None:
    monkeypatch.setattr(rsp_list_service, "read_server_snapshot", _no_snapshot)
    await store_lists(test_session, 11, 1, "B 服", _extras(11, owner=7, admins=[8], bans=[9]))
    await store_lists(test_session, 22, 2, "A 服", _extras(22, owner=1, vips=[9], bans=[9]))
    await test_session.commit()

    found = await list_player_servers(test_session, 9)
    assert [s.name for s in found.ban] == ["A 服", "B 服"]
    assert [s.server_id for s in found.vip] == [22]
    assert found.owner == [] and found.admin == []
    assert found.tracked_servers == 2

    # 再存一次整服替换：9 被解封，旧名单行不残留
    await store_lists(test_session, 11, 3, "B 服 新", _extras(11, owner=7, admins=[8]))
    await test_session.commit()
    found = await list_player_servers(test_session, 9)
    assert [s.server_id for s in found.ban] == [22]
    owner = await list_player_servers(test_session, 7)
    assert [(s.game_id, s.name) for s in owner.owner] == [(3, "B 服 新")]


async def test_lookup_attaches_live_player_count(test_session, monkeypatch) -> None:
    async def snapshot():
        return [_s(1, "x", players=40)]

    monkeypatch.setattr(rsp_list_service, "read_server_snapshot", snapshot)
    await store_lists(test_session, 11, 1, "在线", _extras(11, owner=5))
    await store_lists(test_session, 22, 2, "空服", _extras(22, owner=5))
    await test_session.commit()

    found = await list_player_servers(test_session, 5)
    counts = {s.name: s.player_count for s in found.owner}
    assert counts == {"在线": 40, "空服": None}


async def test_refresh_picks_missing_then_oldest_and_prunes(test_session, monkeypatch) -> None:
    now = datetime.now(UTC)
    test_session.add_all(
        [
            # 刚刷过，不该再拉
            Bf1RspServer(server_id=11, game_id=1, name="a", refreshed_at=now),
            Bf1RspServer(server_id=22, game_id=2, name="b", refreshed_at=now - timedelta(hours=7)),
            Bf1RspServer(server_id=33, game_id=3, name="c", refreshed_at=now - timedelta(hours=9)),
            # 一个月没出现过，清掉
            Bf1RspServer(
                server_id=99, game_id=9, name="gone", refreshed_at=now - timedelta(days=31)
            ),
            Bf1RspMember(server_id=99, role="ban", pid=5),
        ]
    )
    await test_session.commit()

    asked: list[int] = []

    async def fake_extras(self, gid):
        asked.append(gid)
        return _extras(gid * 11, owner=gid), f"新名{gid}"

    monkeypatch.setattr(BF1ServerService, "get_extras", fake_extras)
    monkeypatch.setattr(rsp_list_service, "REFRESH_PER_ROUND", 2)
    summaries = [_s(1, "a"), _s(2, "b"), _s(3, "c"), _s(4, "d"), _s(5, "未解析")]
    server_ids = {1: 11, 2: 22, 3: 33, 4: 44}

    assert await refresh_stale_lists(test_session, summaries, server_ids) == 2
    # 没有名单的先拉，其次是最旧的
    assert asked == [4, 3]
    assert await test_session.get(Bf1RspServer, 99) is None
    assert (
        await test_session.scalars(select(Bf1RspMember).where(Bf1RspMember.pid == 5))
    ).all() == []
    assert (await test_session.get(Bf1RspServer, 44)).name == "新名4"

    assert await refresh_stale_lists(test_session, summaries, server_ids) == 1
    assert asked == [4, 3, 2]


async def test_refresh_stops_on_ea_error(test_session, monkeypatch) -> None:
    async def boom(self, gid):
        raise EAApiError(code="X", message="down")

    monkeypatch.setattr(BF1ServerService, "get_extras", boom)
    assert await refresh_stale_lists(test_session, [_s(1, "a")], {1: 11}) == 0


async def test_detail_writes_back_but_throttled(test_session) -> None:
    await remember_detail_lists(test_session, 1, "详情", _extras(11, owner=5, vips=[6]))
    first = await test_session.get(Bf1RspServer, 11)
    assert first is not None and first.name == "详情"

    # 十分钟内再打开，不重写
    await remember_detail_lists(test_session, 2, "又开", _extras(11, owner=5))
    vip = await test_session.scalar(select(Bf1RspMember).where(Bf1RspMember.role == "vip"))
    assert vip is not None and vip.pid == 6

    # 真官服（无服主）不记
    await remember_detail_lists(test_session, 3, "官服", ServerExtras(server_id=None))
    assert await test_session.get(Bf1RspServer, 3) is None
