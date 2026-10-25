"""全服摘要缓存上的服务器搜索，以及登记服务器人数点的写入、清理与读取。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.api.errors import ValidationError
from app.models.bf1.server_player_count import Bf1ServerPlayerCount
from app.schemas.bf1.server import ServerSummary
from app.services.bf1 import server_service
from app.services.bf1.server_filters import filter_summaries
from app.services.bf1.server_player_count_service import (
    list_player_counts,
    record_player_counts,
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


async def test_record_player_counts_samples_private_servers(test_session) -> None:
    stale = Bf1ServerPlayerCount(
        game_id=1,
        name="mine",
        player_count=1,
        sampled_at=datetime.now(UTC) - timedelta(days=8),
    )
    test_session.add(stale)
    await test_session.commit()

    summaries = [
        _s(1, "mine", players=42, map_name="MP_Forest"),
        _s(2, "official", is_official=True),
        _s(3, "other", players=7),
    ]
    assert await record_player_counts(test_session, summaries) == 2

    rows = (await test_session.scalars(select(Bf1ServerPlayerCount))).all()
    assert sorted((r.game_id, r.name, r.map_name, r.player_count) for r in rows) == [
        (1, "mine", "MP_Forest", 42),
        (3, "other", "MP_Amiens", 7),
    ]
    # 不满 5 分钟的下一轮不采样
    assert await record_player_counts(test_session, summaries) == 0

    points = await list_player_counts(test_session, 1)
    assert [p.players for p in points] == [42]
    assert abs(points[0].ts - datetime.now(UTC).timestamp()) < 60
    assert await list_player_counts(test_session, 2) == []


async def test_list_player_counts_joins_restarts_by_name(test_session) -> None:
    # 服务器重启换了 gameId：用新 gameId 查也能拿到重启前的点
    now = datetime.now(UTC)
    test_session.add_all(
        [
            Bf1ServerPlayerCount(
                game_id=1, name="mine", player_count=10, sampled_at=now - timedelta(hours=2)
            ),
            Bf1ServerPlayerCount(
                game_id=9, name="mine", player_count=20, sampled_at=now - timedelta(hours=1)
            ),
            Bf1ServerPlayerCount(
                game_id=5, name="other", player_count=99, sampled_at=now - timedelta(hours=1)
            ),
        ]
    )
    await test_session.commit()
    assert [p.players for p in await list_player_counts(test_session, 9)] == [10, 20]


async def test_list_player_counts_separates_same_name_servers(test_session) -> None:
    # 两个同名私服同时在线：各查各的；重启前分不清归属的时刻跳过
    now = datetime.now(UTC)
    t0, t1 = now - timedelta(hours=2), now - timedelta(hours=1)
    test_session.add_all(
        [
            Bf1ServerPlayerCount(game_id=1, name="dup", player_count=10, sampled_at=t0),
            Bf1ServerPlayerCount(game_id=2, name="dup", player_count=20, sampled_at=t0),
            Bf1ServerPlayerCount(game_id=3, name="dup", player_count=30, sampled_at=t1),
            Bf1ServerPlayerCount(game_id=2, name="dup", player_count=40, sampled_at=t1),
        ]
    )
    await test_session.commit()
    assert [p.players for p in await list_player_counts(test_session, 2)] == [20, 40]
    assert [p.players for p in await list_player_counts(test_session, 3)] == [30]
