"""全服摘要缓存上的服务器搜索，以及人数点、服务器实例的写入、清理与按实例归并的读取。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.api.errors import ValidationError
from app.models import Server
from app.models.bf1.game_instance import Bf1GameInstance
from app.models.bf1.server_player_count import Bf1ServerPlayerCount
from app.schemas.bf1.server import ServerExtras, ServerSummary
from app.services.bf1 import server_player_count_service, server_service
from app.services.bf1.server_filters import filter_summaries
from app.services.bf1.server_player_count_service import (
    list_map_stats,
    list_player_counts,
    record_player_counts,
    resolve_server_ids,
)
from app.services.bf1.server_service import BF1ServerService
from sqlalchemy import select


def _s(gid: int, name: str, *, players: int = 10, cap: int = 64, **kw: object) -> ServerSummary:
    fields: dict = {
        "map_name": "MP_Amiens",
        "game_mode": "Conquest",
        "region": "Asia",
        **kw,
    }
    return ServerSummary(
        server_id=0,
        game_id=gid,
        name=name,
        player_count=players,
        max_player_count=cap,
        **fields,
    )


ITEMS = [
    _s(1, "[ABC] Amiens 24/7", players=60),
    _s(2, "abc rush", players=20, game_mode="Breakthrough", cap=32),
    _s(3, "EU Fort", players=5, region="EU", map_name="MP_Forest"),
]


def test_filter_summaries_matches_like_ea() -> None:
    # 名称包含匹配、大小写不敏感
    assert [s.game_id for s in filter_summaries(ITEMS, name="ABC")] == [1, 2]
    assert [s.game_id for s in filter_summaries(ITEMS, modes=["Breakthrough"])] == [2]
    assert [s.game_id for s in filter_summaries(ITEMS, regions=["EU"])] == [3]
    assert [s.game_id for s in filter_summaries(ITEMS, maps=["MP_Amiens"], sizes=[32])] == [2]
    # 多值取并集，不传等于不约束
    assert len(filter_summaries(ITEMS, regions=["Asia", "EU"])) == 3
    assert len(filter_summaries(ITEMS)) == 3


def _no_ea(_db: object) -> object:
    raise AssertionError("快照命中时不应请求 EA")


async def test_search_uses_snapshot_sorted_and_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_read() -> list[ServerSummary]:
        return list(reversed(ITEMS))

    monkeypatch.setattr(server_service, "read_server_snapshot", fake_read)
    monkeypatch.setattr(server_service, "get_bf1_client", _no_ea)
    res = await BF1ServerService(object()).search(regions=["Asia"], limit=1)  # type: ignore[arg-type]
    assert res.total == 2
    assert [s.game_id for s in res.items] == [1]


async def test_search_still_validates_on_snapshot_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_read() -> list[ServerSummary]:
        return ITEMS

    monkeypatch.setattr(server_service, "read_server_snapshot", fake_read)
    with pytest.raises(ValidationError):
        await BF1ServerService(object()).search(maps=["MP_Nope"])  # type: ignore[arg-type]


class _FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None

    async def searchServers(self, **_kw: object) -> dict:  # noqa: N802
        self.calls += 1
        return {"result": {"gameservers": [{"name": "empty", "gameId": "9", "serverId": "1"}]}}


@pytest.mark.parametrize("include_empty, cached", [(True, ITEMS), (False, None)])
async def test_search_falls_back_to_ea(
    monkeypatch: pytest.MonkeyPatch, include_empty: bool, cached: list | None
) -> None:
    async def fake_read() -> list[ServerSummary] | None:
        if include_empty:
            raise AssertionError("要空服时不读快照")
        return cached

    client = _FakeClient()
    monkeypatch.setattr(server_service, "read_server_snapshot", fake_read)
    monkeypatch.setattr(server_service, "get_bf1_client", lambda _db: client)
    res = await BF1ServerService(object()).search(include_empty=include_empty)  # type: ignore[arg-type]
    assert client.calls == 1
    assert [s.game_id for s in res.items] == [9]


async def test_search_by_keyword_uses_ea(monkeypatch: pytest.MonkeyPatch) -> None:
    """按名称搜索要能找到空服，快照里没有空服，所以不读快照。"""

    async def fake_read() -> list[ServerSummary] | None:
        raise AssertionError("按名称搜索不读快照")

    client = _FakeClient()
    monkeypatch.setattr(server_service, "read_server_snapshot", fake_read)
    monkeypatch.setattr(server_service, "get_bf1_client", lambda _db: client)
    res = await BF1ServerService(object()).search(keyword="empty")  # type: ignore[arg-type]
    assert client.calls == 1
    assert [s.game_id for s in res.items] == [9]


async def test_record_player_counts_samples_servers_and_instances(test_session) -> None:
    stale = Bf1ServerPlayerCount(
        game_id=1, player_count=1, sampled_at=datetime.now(UTC) - timedelta(days=8)
    )
    gone = Bf1GameInstance(
        game_id=7,
        name="gone",
        first_seen=datetime.now(UTC) - timedelta(days=100),
        last_seen=datetime.now(UTC) - timedelta(days=91),
    )
    test_session.add_all([stale, gone])
    await test_session.commit()

    summaries = [
        _s(1, "mine", players=42, map_name="MP_Forest"),
        _s(2, "[DICE] Official - CQ - EU - #1", is_official=True),
        _s(3, "rented official", is_official=True, has_owner=True),
    ]
    assert await record_player_counts(test_session, summaries, {1: 11}) == 3

    rows = (await test_session.scalars(select(Bf1ServerPlayerCount))).all()
    assert sorted((r.game_id, r.map_name, r.player_count) for r in rows) == [
        (1, "MP_Forest", 42),
        (2, "MP_Amiens", 10),
        (3, "MP_Amiens", 10),
    ]
    instances = (await test_session.scalars(select(Bf1GameInstance))).all()
    # 过期 90 天的实例被清掉；只有 owner 为 0 的 OFFICIAL 才算真官服
    assert sorted((i.game_id, i.server_id, i.official, i.name) for i in instances) == [
        (1, 11, False, "mine"),
        (2, None, True, "[DICE] Official - CQ - EU - #1"),
        (3, None, False, "rented official"),
    ]
    # 同一分钟内重复触发不重复采样
    assert await record_player_counts(test_session, summaries) == 0

    points = await list_player_counts(test_session, 1)
    assert [p.players for p in points] == [42]
    assert abs(points[0].ts - datetime.now(UTC).timestamp()) < 60
    assert await list_player_counts(test_session, 4) == []


async def test_instances_keep_server_id_and_follow_renames(test_session, monkeypatch) -> None:
    clock = [datetime.now(UTC) - timedelta(minutes=5)]

    class _Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return clock[0]

    monkeypatch.setattr(server_player_count_service, "datetime", _Clock)
    await record_player_counts(test_session, [_s(1, "old name")], {1: 11})
    clock[0] += timedelta(minutes=1)
    # 解析失败的一轮没带 serverId，不能把已知的冲掉；改名跟着最新的走
    await record_player_counts(test_session, [_s(1, "new name")], {})
    inst = await test_session.scalar(select(Bf1GameInstance))
    assert (inst.server_id, inst.name) == (11, "new name")
    assert inst.last_seen.replace(tzinfo=UTC) == clock[0]
    assert inst.first_seen.replace(tzinfo=UTC) == clock[0] - timedelta(minutes=1)


def _instance(gid: int, server_id: int | None, name: str = "x") -> Bf1GameInstance:
    now = datetime.now(UTC)
    return Bf1GameInstance(
        game_id=gid, server_id=server_id, name=name, first_seen=now, last_seen=now
    )


async def test_list_player_counts_joins_restarts_by_server_id(test_session) -> None:
    # 服务器重启换了 gameId、还改了名：按 serverId 连上重启前的点，别家服不混进来
    now = datetime.now(UTC)
    t0, t1 = now - timedelta(hours=2), now - timedelta(hours=1)
    test_session.add_all(
        [
            _instance(1, 11, "old"),
            _instance(2, 22, "old"),
            _instance(3, 11, "new"),
            Bf1ServerPlayerCount(game_id=1, player_count=10, sampled_at=t0),
            Bf1ServerPlayerCount(game_id=2, player_count=99, sampled_at=t0),
            Bf1ServerPlayerCount(game_id=3, player_count=20, sampled_at=t1),
        ]
    )
    await test_session.commit()
    assert [p.players for p in await list_player_counts(test_session, 3)] == [10, 20]
    assert [p.players for p in await list_player_counts(test_session, 1)] == [10, 20]
    assert [p.players for p in await list_player_counts(test_session, 2)] == [99]


async def test_list_player_counts_unresolved_instance_stands_alone(test_session) -> None:
    # 还没解析到 serverId（或真官服）只看自己这个实例，同名的服不再按名字混在一起
    now = datetime.now(UTC)
    t0, t1 = now - timedelta(hours=2), now - timedelta(hours=1)
    test_session.add_all(
        [
            _instance(1, None, "dup"),
            _instance(2, None, "dup"),
            Bf1ServerPlayerCount(game_id=1, player_count=10, sampled_at=t0),
            Bf1ServerPlayerCount(game_id=2, player_count=20, sampled_at=t0),
            Bf1ServerPlayerCount(game_id=2, player_count=40, sampled_at=t1),
        ]
    )
    await test_session.commit()
    assert [p.players for p in await list_player_counts(test_session, 2)] == [20, 40]
    assert [p.players for p in await list_player_counts(test_session, 1)] == [10]


async def test_list_player_counts_overlapping_instances_prefer_own(test_session) -> None:
    # 重启那一分钟新旧两个实例都在快照里：同一时刻只取一个，优先查的那个
    t0 = datetime.now(UTC) - timedelta(hours=1)
    test_session.add_all(
        [
            _instance(1, 11),
            _instance(2, 11),
            Bf1ServerPlayerCount(game_id=1, player_count=10, sampled_at=t0),
            Bf1ServerPlayerCount(game_id=2, player_count=1, sampled_at=t0),
        ]
    )
    await test_session.commit()
    assert [p.players for p in await list_player_counts(test_session, 2)] == [1]
    assert [p.players for p in await list_player_counts(test_session, 1)] == [10]


async def test_resolve_server_ids_caches_and_skips_true_official(test_session, monkeypatch) -> None:
    class _Cache:
        def __init__(self) -> None:
            self.data: dict = {"bf1:gid_server_id:3": 33}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, ttl=None):
            self.data[key] = value

    cache = _Cache()
    asked: list[int] = []

    async def fake_get_cache():
        return cache

    async def fake_extras(self, gid):
        asked.append(gid)
        if gid == 2:
            return None
        return ServerExtras(server_id={1: 11, 6: 66}.get(gid)), "x"

    monkeypatch.setattr(server_player_count_service, "get_cache", fake_get_cache)
    monkeypatch.setattr(BF1ServerService, "get_extras", fake_extras)
    monkeypatch.setattr(server_player_count_service, "RESOLVE_PER_ROUND", 3)
    registered = Server(game="bf1", server_id=11, game_id=999, name="mine")
    test_session.add(registered)
    await test_session.commit()

    summaries = [
        _s(1, "mine"),
        _s(2, "no rsp"),
        _s(3, "cached"),
        _s(5, "official", is_official=True),
        _s(6, "rented official", is_official=True, has_owner=True),
        _s(4, "over budget"),
    ]
    assert await resolve_server_ids(test_session, summaries) == {1: 11, 3: 33, 6: 66}
    # 每轮最多问 3 个；真官服不问；查不到的记 0，下一轮不再占名额
    assert asked == [1, 2, 6]
    assert cache.data["bf1:gid_server_id:2"] == 0
    await test_session.refresh(registered)
    assert registered.game_id == 1

    assert await resolve_server_ids(test_session, summaries) == {1: 11, 3: 33, 6: 66}
    assert asked == [1, 2, 6, 4]


async def test_list_map_stats_aggregates_minutes_and_rounds(test_session) -> None:
    # 亚眠 3 分钟 → 西奈 2 分钟 → 空服 30 分钟 → 亚眠 1 分钟：亚眠两轮，西奈一轮
    base = datetime.now(UTC) - timedelta(hours=1)

    def at(minute: int, map_name: str, players: int) -> Bf1ServerPlayerCount:
        return Bf1ServerPlayerCount(
            game_id=1,
            map_name=map_name,
            game_mode="Conquest",
            player_count=players,
            sampled_at=base + timedelta(minutes=minute),
        )

    test_session.add_all(
        [
            at(0, "MP_Amiens", 60),
            at(1, "MP_Amiens", 60),
            at(2, "MP_Amiens", 60),
            at(3, "MP_Desert", 30),
            at(4, "MP_Desert", 30),
            at(35, "MP_Amiens", 10),
        ]
    )
    await test_session.commit()

    stats = await list_map_stats(test_session, 1)
    amiens, desert = stats
    assert (amiens.map_name, amiens.rounds, amiens.minutes) == ("MP_Amiens", 2, 4)
    assert amiens.player_minutes == 190
    assert amiens.avg_players == 47.5
    assert amiens.map_display_name and amiens.map_image_url
    # 西奈第二个点后间隔 31 分钟，视为断档只算 1 分钟
    assert (desert.rounds, desert.minutes, desert.player_minutes) == (1, 2, 60)

    points = await list_player_counts(test_session, 1)
    assert [p.map_name for p in points][:4] == ["MP_Amiens"] * 3 + ["MP_Desert"]
