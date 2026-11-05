"""BF6 对局估算：快照做差、记录与复查节奏、接口（上游全部打桩）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.api.deps import get_session_factory
from app.domain.games.bf6 import client as bf6
from app.domain.games.bf6.wire import CategoryStats, Dimension, DimensionedStat, Player, PlayerStats
from app.models.bf6_match import Bf6MatchEstimate, Bf6StatSnapshot
from app.services.bf6 import credential_service, match_service, player_service
from app.services.bf6.match_delta import diff
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
NID = 1008067890273

BASE: dict[str, int] = {
    "matches_gm_all": 100,
    "wins_gm_all": 60,
    "losses_gm_all": 40,
    "tp_kit": 360_000,
    "score_total": 500_000,
    "Kills_Total": 3000,
    "human_kills_total": 2500,
    "deaths_total": 2000,
    "matches_gm_cq": 80,
    "wins_gm_cq": 50,
    "losses_gm_cq": 30,
    "matches_gm_mp": 100,
    "matches_lvlmpaftermath": 10,
    "matches_lvlmp": 100,
    "kw_wp_ar_m4a1": 500,
    "tp_wp_ar_m4a1": 30_000,
    "kw_wp_ar": 900,
    "kw_wp_temp": 2400,
    "tp_kit_assault": 200_000,
    "tp_kit_support": 100_000,
    "kw_veh_air_uh06": 40,
    "kw_veh_air": 40,
}


def _after(base: dict[str, int], **changes: int) -> dict[str, int]:
    out = dict(base)
    for name, inc in changes.items():
        out[name] = out.get(name, 0) + inc
    return out


ONE_CQ_WIN = _after(
    BASE,
    matches_gm_all=1,
    wins_gm_all=1,
    matches_gm_cq=1,
    wins_gm_cq=1,
    matches_gm_mp=1,
    matches_lvlmpaftermath=1,
    matches_lvlmp=1,
    tp_kit=1500,
    score_total=6000,
    Kills_Total=30,
    human_kills_total=25,
    deaths_total=10,
    kw_wp_ar_m4a1=20,
    tp_wp_ar_m4a1=1200,
    kw_wp_ar=20,
    kw_wp_temp=20,
    kw_wp_smg_pw7a2=5,
    tp_kit_assault=1500,
)


# ---------------------------------------------------------------------------
# 做差
# ---------------------------------------------------------------------------


def test_single_match_delta() -> None:
    delta = diff(BASE, ONE_CQ_WIN)
    assert delta is not None
    assert (delta.matches, delta.wins, delta.losses) == (1, 1, 0)
    # 汇总行（mp、全部地图）不算具体模式和地图
    assert [(m.id, m.matches, m.wins) for m in delta.modes] == [("cq", 1, 1)]
    assert [m.id for m in delta.maps] == ["mpaftermath"]
    assert (delta.kills, delta.human_kills, delta.deaths) == (30, 25, 10)
    assert delta.kd == 2.5
    assert delta.kpm == 1.0
    assert delta.kit == "assault"
    # 大类汇总和全部合计不当成武器；新出现的武器（上次没有这一行）照样算
    assert [(w.id, w.kills) for w in delta.weapons] == [("ar_m4a1", 20), ("smg_pw7a2", 5)]
    assert delta.vehicles == []


def test_merged_matches_keep_per_mode_counts() -> None:
    cur = _after(
        ONE_CQ_WIN,
        matches_gm_all=2,
        losses_gm_all=2,
        matches_gm_cq=1,
        losses_gm_cq=1,
        matches_gm_bt=1,
        losses_gm_bt=1,
        tp_kit=2000,
    )
    delta = diff(BASE, cur)
    assert delta is not None
    assert (delta.matches, delta.wins, delta.losses) == (3, 1, 2)
    assert [(m.id, m.matches) for m in delta.modes] == [("cq", 2), ("bt", 1)]


def test_no_play_or_rollback_is_not_a_match() -> None:
    # 只是经验之类变了
    assert diff(BASE, _after(BASE, xp_all=500)) is None
    # EA 那边累计值变小：不当成对局，也不出负数
    assert diff(ONE_CQ_WIN, _after(BASE, tp_kit=9999)) is None


def test_time_without_finished_match() -> None:
    # 中途退出：有战斗时间但没计场次
    delta = diff(BASE, _after(BASE, tp_kit=600, Kills_Total=5, human_kills_total=5))
    assert delta is not None
    assert delta.matches == 0
    assert delta.modes == []
    assert delta.kd is None  # 没死过


# ---------------------------------------------------------------------------
# 记录与复查
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory(test_session):
    return async_sessionmaker(test_session.bind, expire_on_commit=False, autoflush=False)


async def _snapshot(session_factory) -> Bf6StatSnapshot | None:
    async with session_factory() as db:
        return await db.get(Bf6StatSnapshot, NID)


async def _estimates(session_factory) -> int:
    async with session_factory() as db:
        return await db.scalar(select(func.count()).select_from(Bf6MatchEstimate)) or 0


async def test_record_starts_on_view_and_diffs_later(session_factory) -> None:
    # 后台复查不会替没人看过的玩家开始记录
    await match_service.record(session_factory, NID, BASE, T0, viewed=False)
    assert await _snapshot(session_factory) is None

    assert await match_service.record(session_factory, NID, BASE, T0, viewed=True) is None
    assert await _snapshot(session_factory) is not None

    t1 = T0 + timedelta(minutes=10)
    assert await match_service.record(session_factory, NID, BASE, t1, viewed=False) is None
    t2 = T0 + timedelta(minutes=20)
    delta = await match_service.record(session_factory, NID, ONE_CQ_WIN, t2, viewed=False)
    assert delta is not None and delta.matches == 1

    listing = await match_service.list_estimates(session_factory, NID)
    assert listing.tracked_since == T0
    assert listing.last_checked_at == t2
    [item] = listing.matches
    # 对局在上一次读到旧值之后结束
    assert item.started_after == t1
    assert item.observed_at == t2
    assert item.modes[0].id == "cq"

    # 后台复查不刷新查看时间
    snap = await _snapshot(session_factory)
    assert snap is not None
    assert match_service._aware(snap.viewed_at) == T0
    assert match_service._aware(snap.changed_at) == t2

    # 同样的数据再读一次不产生新的估算
    await match_service.record(
        session_factory, NID, ONE_CQ_WIN, t2 + timedelta(minutes=10), viewed=False
    )
    assert await _estimates(session_factory) == 1


async def test_due_players_follow_activity(session_factory) -> None:
    await match_service.record(session_factory, NID, BASE, T0, viewed=True)

    # 刚有变化：10 分钟后到期
    assert await match_service.due_players(session_factory, T0 + timedelta(minutes=9)) == []
    assert await match_service.due_players(session_factory, T0 + timedelta(minutes=10)) == [NID]

    # 两小时没变化：放宽到 30 分钟
    idle = T0 + timedelta(hours=3)
    await match_service.record(session_factory, NID, BASE, idle, viewed=False)
    assert await match_service.due_players(session_factory, idle + timedelta(minutes=20)) == []
    assert await match_service.due_players(session_factory, idle + timedelta(minutes=30)) == [NID]

    # 一周没人看就不再复查
    assert await match_service.due_players(session_factory, T0 + timedelta(days=8)) == []


async def test_touch_keeps_tracking(session_factory) -> None:
    await match_service.record(session_factory, NID, BASE, T0, viewed=True)
    later = T0 + timedelta(days=6)
    await match_service.touch(session_factory, NID, later)
    assert await match_service.due_players(session_factory, T0 + timedelta(days=8)) == [NID]


async def test_poll_once_records_and_skips_missing(session_factory) -> None:
    other = 42
    await match_service.record(session_factory, NID, BASE, T0, viewed=True)
    await match_service.record(session_factory, other, BASE, T0, viewed=True)
    asked: list[list[int]] = []

    async def fetch(ids: list[int]) -> dict[int, dict[str, int]]:
        asked.append(sorted(ids))
        return {NID: ONE_CQ_WIN}

    t1 = T0 + timedelta(minutes=10)
    assert await match_service.poll_once(session_factory, fetch, t1) == 2
    assert asked == [[other, NID]]
    assert await _estimates(session_factory) == 1
    # 没读到的人也算复查过，不会一直占着队首
    assert await match_service.due_players(session_factory, t1 + timedelta(minutes=5)) == []


async def test_purge_drops_stale_rows(session_factory) -> None:
    await match_service.record(session_factory, NID, BASE, T0, viewed=True)
    await match_service.record(
        session_factory, NID, ONE_CQ_WIN, T0 + timedelta(minutes=10), viewed=False
    )
    await match_service.purge_expired(session_factory, T0 + timedelta(days=30))
    assert await _snapshot(session_factory) is not None
    assert await _estimates(session_factory) == 1
    await match_service.purge_expired(session_factory, T0 + timedelta(days=91))
    assert await _snapshot(session_factory) is None
    assert await _estimates(session_factory) == 0


async def test_poller_backs_off_when_unavailable(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def fetch(ids: list[int]) -> dict[int, dict[str, int]]:
        raise credential_service.Bf6NotConfiguredError("没填")

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        raise RuntimeError("stop")

    monkeypatch.setattr(match_service.asyncio, "sleep", sleep)
    # 立刻到期
    await match_service.record(
        session_factory, NID, BASE, datetime.now(UTC) - timedelta(hours=1), viewed=True
    )
    with pytest.raises(RuntimeError):
        await match_service.tracker_poller(session_factory, fetch)
    assert sleeps == [match_service._UNAVAILABLE_BACKOFF_SECONDS]


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


def _player(nucleus_id: int, stats: dict[str, int]) -> PlayerStats:
    rows = tuple(
        DimensionedStat(name, value, (Dimension("global", "global"),))
        for name, value in stats.items()
    )
    return PlayerStats(
        player=Player(nucleus_id=nucleus_id, platform=7),
        categories=(CategoryStats("glacier_mp", dimensioned_stats=rows),),
    )


@pytest.fixture
def api(client, session_factory, monkeypatch: pytest.MonkeyPatch):
    client._transport.app.dependency_overrides[get_session_factory] = lambda: session_factory
    store: dict[str, Any] = {}

    async def get(key: str) -> Any:
        return store.get(key)

    async def set_(key: str, value: Any, ttl: int) -> None:
        store[key] = value

    async def session_jwt(_sf, *, renew: bool = False) -> str:
        return "jwt"

    monkeypatch.setattr(player_service, "_cache_get", get)
    monkeypatch.setattr(player_service, "_cache_set", set_)
    monkeypatch.setattr(credential_service, "get_session_jwt", session_jwt)
    return client, store


async def test_stats_view_starts_tracking_and_batch_refreshes(
    api, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, store = api
    current = {NID: BASE}

    async def get_stats(token: str, ids: list[int]) -> list[PlayerStats]:
        return [_player(nid, current[nid]) for nid in ids if nid in current]

    monkeypatch.setattr(bf6, "get_stats", get_stats)

    resp = await client.get(f"/api/v1/bf6/players/{NID}/matches")
    assert resp.status_code == 200
    assert resp.json() == {
        "tracking": False,
        "tracked_since": None,
        "last_checked_at": None,
        "matches": [],
    }

    assert (await client.get(f"/api/v1/bf6/players/{NID}/stats")).status_code == 200
    body = (await client.get(f"/api/v1/bf6/players/{NID}/matches")).json()
    assert body["tracking"] is True
    assert body["matches"] == []

    # 后台复查读到一局，顺带刷新战绩缓存
    current[NID] = ONE_CQ_WIN
    fetched = await player_service.fetch_batch(session_factory, [NID, 7])
    assert set(fetched) == {NID}
    await match_service.record(
        session_factory, NID, fetched[NID], datetime.now(UTC) + timedelta(seconds=1), viewed=False
    )
    assert store[f"bf6:stats:v2:{NID}"]["career"]["kills"] == ONE_CQ_WIN["Kills_Total"]

    body = (await client.get(f"/api/v1/bf6/players/{NID}/matches")).json()
    [match] = body["matches"]
    assert match["matches"] == 1
    assert match["wins"] == 1
    assert match["maps"][0]["id"] == "mpaftermath"
    assert match["weapons"][0]["id"] == "ar_m4a1"


async def test_stats_still_served_when_snapshot_write_fails(
    api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import OperationalError

    client, _store = api

    async def get_stats(token: str, ids: list[int]) -> list[PlayerStats]:
        return [_player(ids[0], BASE)]

    async def broken(*_a: Any, **_k: Any) -> None:
        raise OperationalError("insert", {}, Exception("db down"))

    monkeypatch.setattr(bf6, "get_stats", get_stats)
    monkeypatch.setattr(match_service, "record", broken)
    resp = await client.get(f"/api/v1/bf6/players/{NID}/stats")
    assert resp.status_code == 200
    assert resp.json()["career"]["kills"] == BASE["Kills_Total"]
