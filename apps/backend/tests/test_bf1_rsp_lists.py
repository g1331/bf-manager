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


async def test_managed_servers_by_personas(test_session, monkeypatch) -> None:
    from app.services.bf1.rsp_list_service import list_managed_servers

    monkeypatch.setattr(rsp_list_service, "read_server_snapshot", _no_snapshot)
    await store_lists(test_session, 11, 1, "B 服", _extras(11, owner=7, admins=[8], vips=[9]))
    await store_lists(test_session, 22, 2, "A 服", _extras(22, owner=8, admins=[7]))
    await test_session.commit()

    assert await list_managed_servers(test_session, []) == []
    # VIP 不算；按服名排，同一台服服主在前
    got = [
        (pid, role, s.name) for pid, role, s in await list_managed_servers(test_session, [7, 8, 9])
    ]
    assert got == [
        (8, "owner", "A 服"),
        (7, "admin", "A 服"),
        (7, "owner", "B 服"),
        (8, "admin", "B 服"),
    ]
    assert await list_managed_servers(test_session, [9]) == []


async def test_refresh_follows_new_game_id_without_refetch(test_session, monkeypatch) -> None:
    now = datetime.now(UTC)
    test_session.add(Bf1RspServer(server_id=11, game_id=1, name="a", refreshed_at=now))
    await test_session.commit()
    asked: list[int] = []

    async def fake_extras(self, gid):
        asked.append(gid)

    monkeypatch.setattr(BF1ServerService, "get_extras", fake_extras)
    # 服务器重启换了 gameId：名单刚刷过不重拉，只把 gameId 改成新的
    assert await refresh_stale_lists(test_session, [_s(7, "a")], {7: 11}) == 0
    assert asked == []
    srv = await test_session.get(Bf1RspServer, 11)
    await test_session.refresh(srv)
    assert srv.game_id == 7


async def test_refresh_keeps_game_id_while_old_and_new_instances_overlap(
    test_session, monkeypatch
) -> None:
    now = datetime.now(UTC)
    # 解析 serverId 时已按新实例写成 7
    test_session.add(Bf1RspServer(server_id=11, game_id=7, name="a", refreshed_at=now))
    await test_session.commit()

    async def fake_extras(self, gid):
        return

    monkeypatch.setattr(BF1ServerService, "get_extras", fake_extras)
    # 重启那一分钟旧实例 1 还在快照里，排在新实例后面：不能改回旧的
    await refresh_stale_lists(test_session, [_s(7, "a"), _s(1, "a")], {7: 11, 1: 11})
    srv = await test_session.get(Bf1RspServer, 11)
    await test_session.refresh(srv)
    assert srv.game_id == 7
    # sqlite 读回的是无时区时间，留在会话里会让清理过期服时的比较出错
    test_session.expunge_all()
    # 两个都不是记的那个时也分不清，先不动
    await refresh_stale_lists(test_session, [_s(8, "a"), _s(9, "a")], {8: 11, 9: 11})
    assert (await test_session.get(Bf1RspServer, 11)).game_id == 7


def _search_returns(monkeypatch, items: list[ServerSummary], calls: list[int]) -> None:
    from app.schemas.bf1.server import ServerListResponse

    async def search(self, keyword=None, **kw):
        assert kw["include_empty"] is True
        return ServerListResponse(total=len(items), items=items)

    async def extras(self, gid):
        calls.append(gid)
        # gameId 9 是这台服重启后的新实例，8 是同名的另一台
        return (_extras(11 if gid == 9 else 22, owner=5), "空服")

    monkeypatch.setattr(BF1ServerService, "search", search)
    monkeypatch.setattr(BF1ServerService, "get_extras", extras)


async def test_locate_keeps_current_game_id_without_detail_calls(test_session, monkeypatch) -> None:
    await store_lists(test_session, 11, 7, "空服", _extras(11, owner=5))
    await test_session.commit()
    calls: list[int] = []
    _search_returns(monkeypatch, [_s(7, "空服", 0), _s(9, "空服二号", 0)], calls)
    assert await rsp_list_service.locate_game_id(test_session, 11) == 7
    assert calls == []


async def test_locate_finds_new_instance_and_writes_back(test_session, monkeypatch) -> None:
    await store_lists(test_session, 11, 7, "空服", _extras(11, owner=5))
    await test_session.commit()
    test_session.expunge_all()
    calls: list[int] = []
    # 服务器重启换了 gameId，名单记的 7 已经搜不到；同名的两台逐个核对 serverId
    _search_returns(monkeypatch, [_s(8, "空服", 0), _s(9, "空服", 0), _s(3, "空服 别的", 0)], calls)
    assert await rsp_list_service.locate_game_id(test_session, 11) == 9
    assert calls == [8, 9]
    test_session.expunge_all()
    assert (await test_session.get(Bf1RspServer, 11)).game_id == 9


async def test_locate_returns_none_when_untracked_or_gone(test_session, monkeypatch) -> None:
    calls: list[int] = []
    _search_returns(monkeypatch, [], calls)
    assert await rsp_list_service.locate_game_id(test_session, 11) is None
    await store_lists(test_session, 11, 7, "空服", _extras(11, owner=5))
    await test_session.commit()
    assert await rsp_list_service.locate_game_id(test_session, 11) is None
    assert calls == []


async def test_locate_without_lists_keeps_members(test_session, monkeypatch) -> None:
    from app.schemas.bf1.server import ServerListResponse

    await store_lists(test_session, 11, 7, "空服", _extras(11, owner=5, admins=[6]))
    await test_session.commit()

    async def search(self, keyword=None, **kw):
        return ServerListResponse(total=1, items=[_s(9, "空服", 0)])

    async def extras(self, gid):
        # 详情里只有 serverInfo、没有 rspInfo：服主和名单都是空的
        return ServerExtras(server_id=11), "空服"

    monkeypatch.setattr(BF1ServerService, "search", search)
    monkeypatch.setattr(BF1ServerService, "get_extras", extras)
    assert await rsp_list_service.locate_game_id(test_session, 11) == 9
    test_session.expunge_all()
    assert (await test_session.get(Bf1RspServer, 11)).game_id == 9
    members = await test_session.scalars(
        select(Bf1RspMember.pid).where(Bf1RspMember.server_id == 11)
    )
    assert sorted(members.all()) == [5, 6]
