"""对局：单局战绩编码、生涯差分跟踪器，以及落库后的三种查询。"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from app.api.errors import NotFoundError
from app.core import ea_metrics
from app.domain.games.bf1.round_stats import (
    DEATHS,
    FINISHED,
    KILLS,
    KIT_BASE,
    LEFT_EARLY,
    LOSSES,
    PROBE_NAMES,
    RECHECK_NAMES,
    ROUND_STATS,
    ROUNDS,
    SCORE,
    SUSPECT,
    WINS,
    decode_entries,
    diff,
    encode_entry,
    pack_pids,
    to_vector,
    unpack_pids,
)
from app.models.bf1.game_instance import Bf1GameInstance
from app.models.bf1.rounds import Bf1PlayerRoundDay
from app.services.bf1 import round_service
from app.services.bf1.match_tracker import RECHECK_AFTER, ClosedRound, MatchTracker, RoundLine
from app.services.bf1.server_roster_service import QUEUE, TEAM1, TEAM2
from sqlalchemy import select

N = len(ROUND_STATS)


def test_entry_codec_roundtrip_and_sparse() -> None:
    delta = [0] * N
    delta[KILLS], delta[DEATHS], delta[SCORE], delta[N - 1] = 23, 17, 5840, 1620
    blob = encode_entry(123456, 2, SUSPECT, delta) + encode_entry(7, 1, FINISHED, [0] * N)
    assert decode_entries(blob) == [
        (123456, 2, SUSPECT, {KILLS: 23, DEATHS: 17, SCORE: 5840, N - 1: 1620}),
        (7, 1, FINISHED, {}),
    ]
    # 3 字节 id + 1 字节队伍状态 + 1 字节个数 + 4 项（间隔与值共 2–4 字节）
    assert len(encode_entry(123456, 2, SUSPECT, delta)) <= 20


def test_pids_pack_and_vector_diff() -> None:
    pids = [1005811915302, 1003517866915, 1601233727, 1003517866915]
    assert unpack_pids(pack_pids(pids)) == sorted(set(pids))
    assert len(pack_pids(pids)) < 8 * 3
    v = to_vector({"kills": 3.0, "c___kak_g": 1.6, "nonexistent": 9})
    assert (v[KILLS], v[6], len(v)) == (3, 2, N)
    assert diff([1, 2], [1, 1]) == [0, 1]
    assert diff([1, 0], [1, 1]) is None


class Career:
    """假的 Blaze：按 pid 存生涯向量，fetch 按统计名返回。"""

    def __init__(self) -> None:
        self.vec: dict[int, list[int]] = {}
        self.calls: list[tuple[list[int], dict[str, list[str]]]] = []
        self.fail = False

    def add(self, pid: int, **kw: int) -> None:
        v = self.vec.setdefault(pid, [100] * N)
        idx = {"k": KILLS, "d": DEATHS, "s": SCORE, "w": WINS, "l": LOSSES, "r": ROUNDS}
        for k, n in kw.items():
            v[idx[k]] += n

    def settle(self, winners: list[int], losers: list[int]) -> None:
        for p in winners:
            self.add(p, k=10, d=5, s=3000, w=1, r=1)
        for p in losers:
            self.add(p, k=4, d=9, s=1500, l=1, r=1)

    async def fetch(self, pids: list[int], names: dict[str, list[str]]) -> dict:
        if self.fail:
            raise RuntimeError("blaze down")
        self.calls.append((pids, names))
        wanted = {n for ns in names.values() for n in ns}
        return {
            p: {
                name: float(self.vec[p][i])
                for i, (_, name) in enumerate(ROUND_STATS)
                if name in wanted
            }
            for p in pids
            if p in self.vec
        }


MAP = {1: ("MP_Amiens", "Conquest0")}


def _roster(**slots: int) -> dict:
    return {1: {int(k[1:]): (v, k) for k, v in slots.items()}}


async def test_tracker_full_round_with_leaver_and_settlement() -> None:
    career, tr = Career(), MatchTracker()
    for p in (1, 2, 3, 4, 5, 6):
        career.add(p)
    t0 = 1_800_000_000
    assert (
        await tr.tick(_roster(p1=TEAM1, p2=TEAM1, p3=TEAM2, p4=TEAM2), MAP, t0, career.fetch) == []
    )
    # 5 进服排队后上场；3 中途退出，退出时立刻写入（不加局数）
    career.add(3, k=3, d=2, s=500)
    await tr.tick(_roster(p1=TEAM1, p2=TEAM1, p4=TEAM2, p5=QUEUE), MAP, t0 + 60, career.fetch)
    await tr.tick(_roster(p1=TEAM1, p2=TEAM1, p4=TEAM2, p5=TEAM2), MAP, t0 + 120, career.fetch)
    # 结算：探测到后先不收尾；同一轮进来的 6 属于下一局。5 在结算前一刻换到了 1 队
    career.settle(winners=[1, 2], losers=[4, 5])
    switched = _roster(p1=TEAM1, p2=TEAM1, p4=TEAM2, p5=TEAM1, p6=TEAM1)
    assert await tr.tick(switched, {1: ("MP_Desert", "Conquest0")}, t0 + 180, career.fetch) == []
    # 收尾这一轮换图重新分了队，不能拿来当上一局的队伍
    scrambled = _roster(p1=TEAM2, p2=TEAM1, p4=TEAM1, p5=TEAM1, p6=TEAM2)
    [closed] = await tr.tick(scrambled, {1: ("MP_Desert", "Conquest0")}, t0 + 240, career.fetch)
    roster = _roster(p1=TEAM1, p2=TEAM1, p4=TEAM2, p5=TEAM2, p6=TEAM1)

    assert (closed.game_id, closed.ended_at, closed.winner) == (1, t0 + 180, 1)
    assert (closed.observed_start, closed.settled) == (False, True)
    assert (closed.map_name, closed.game_mode) == ("MP_Amiens", "Conquest0")
    lines = {ln.pid: ln for ln in closed.lines}
    assert sorted(lines) == [1, 2, 3, 4, 5]
    assert (lines[1].status, lines[1].team, lines[1].delta[KILLS], lines[1].delta[WINS]) == (
        FINISHED,
        1,
        10,
        1,
    )
    assert (lines[5].status, lines[5].team, lines[5].delta[LOSSES]) == (FINISHED, 2, 1)
    assert (lines[2].team, lines[4].team) == (1, 2)
    assert (lines[3].status, lines[3].delta[KILLS], lines[3].delta[ROUNDS]) == (LEFT_EARLY, 3, 0)

    # 下一局：在服的人带着结算后的值作基线，开局可见
    career.settle(winners=[4, 5], losers=[1, 2, 6])
    assert await tr.tick(roster, MAP, t0 + 300, career.fetch) == []
    [second] = await tr.tick(roster, MAP, t0 + 360, career.fetch)
    assert (second.started_at, second.observed_start, second.winner) == (t0 + 180, True, 2)
    assert {ln.pid: ln.delta[KILLS] for ln in second.lines} == {1: 4, 2: 4, 4: 10, 5: 10, 6: 4}


async def test_tracker_recheck_drops_late_settlement_from_other_server() -> None:
    career, tr = Career(), MatchTracker()
    for p in (1, 2, 3):
        career.add(p)
    t0 = 1_800_000_000
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2), MAP, t0, career.fetch)
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2, p3=TEAM2), MAP, t0 + 60, career.fetch)
    # 3 上一台服的结算几分钟后才写入：复查时换基线
    career.add(3, l=1, r=1, s=200)
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2, p3=TEAM2), MAP, t0 + 60 + RECHECK_AFTER, career.fetch)
    career.settle(winners=[1], losers=[2, 3])
    t = t0 + 120 + RECHECK_AFTER
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2, p3=TEAM2), MAP, t, career.fetch)
    [closed] = await tr.tick(_roster(p1=TEAM1, p2=TEAM2, p3=TEAM2), MAP, t + 60, career.fetch)
    lines = {ln.pid: ln for ln in closed.lines}
    assert (lines[3].status, lines[3].delta[ROUNDS], lines[3].delta[SCORE]) == (FINISHED, 1, 1500)


async def test_tracker_single_late_write_is_not_a_settlement() -> None:
    career, tr = Career(), MatchTracker()
    for p in (1, 2, 3, 4):
        career.add(p)
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p2=TEAM1, p3=TEAM2, p4=TEAM2)
    await tr.tick(roster, MAP, t0, career.fetch)
    career.add(1, w=1, r=1)  # 只有一个人局数 +1
    await tr.tick(roster, MAP, t0 + 60, career.fetch)
    assert tr.rounds[1].settle_seen_at is None


async def test_tracker_vanished_server_and_failures() -> None:
    career, tr = Career(), MatchTracker()
    for p in (1, 2):
        career.add(p)
    t0 = 1_800_000_000
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2), MAP, t0, career.fetch)
    # 查询失败：状态保留，下一轮重试
    career.fail = True
    career.add(1, k=2, s=100)
    assert await tr.tick({}, {}, t0 + 60, career.fetch) == []
    career.fail = False
    [closed] = await tr.tick({}, {}, t0 + 120, career.fetch)
    assert (closed.settled, closed.winner, [ln.pid for ln in closed.lines]) == (False, None, [1])
    assert 1 not in tr.rounds
    # 断档太久：丢掉状态从头来
    await tr.tick(_roster(p1=TEAM1), MAP, t0 + 180, career.fetch)
    await tr.tick(_roster(p1=TEAM1), MAP, t0 + 1000, career.fetch)
    assert tr.rounds[1].started_at == t0 + 1000


def _closed(game_id: int, ended: int, lines: list[RoundLine]) -> ClosedRound:
    return ClosedRound(
        game_id=game_id,
        started_at=ended - 1800,
        ended_at=ended,
        observed_start=True,
        settled=True,
        map_name="MP_Amiens",
        game_mode="Conquest0",
        winner=1,
        lines=lines,
    )


def _delta(kills: int, *, win: bool | None, seconds: int = 1200) -> list[int]:
    d = [0] * N
    d[KILLS], d[DEATHS], d[SCORE] = kills, 5, kills * 300
    d[KIT_BASE + 2] = seconds  # 突击兵在场秒数
    if win is not None:
        d[WINS if win else LOSSES], d[ROUNDS] = 1, 1
    return d


async def test_save_and_query_rounds(test_session) -> None:
    now = datetime.now(UTC)
    t1 = int((now - timedelta(hours=2)).timestamp())
    t2 = int((now - timedelta(hours=1)).timestamp())
    test_session.add_all(
        [
            Bf1GameInstance(game_id=10, server_id=99, name="old", first_seen=now, last_seen=now),
            Bf1GameInstance(game_id=11, server_id=99, name="mine", first_seen=now, last_seen=now),
        ]
    )
    await test_session.commit()
    a, b = 1005811915302, 1003517866915
    await round_service.save_rounds(
        test_session,
        [
            _closed(10, t1, [RoundLine(a, 1, FINISHED, _delta(20, win=True))]),
            _closed(
                11,
                t2,
                [
                    RoundLine(a, 1, FINISHED, _delta(30, win=True)),
                    RoundLine(b, 2, LEFT_EARLY, _delta(2, win=None, seconds=0)),
                ],
            ),
        ],
    )
    # 同一天的两局追加在同一行
    rows = (await test_session.scalars(select(Bf1PlayerRoundDay))).all()
    assert len([r for r in rows if r.pid == a]) in (1, 2)  # 两局跨 UTC 零点时会落在两行

    page = await round_service.list_server_rounds(test_session, 11)
    assert [(r.game_id, r.server_name, r.player_count) for r in page.items] == [
        (11, "mine", 2),
        (10, "old", 1),
    ]
    assert page.next_before is None
    first = await round_service.list_server_rounds(test_session, 10, limit=1)
    assert first.next_before == t2 and len(first.items) == 1

    detail = await round_service.get_round(test_session, page.items[0].id)
    assert detail.map_display_name and detail.team1_faction
    pa, pb = detail.players
    assert (pa.persona_id, pa.won, pa.kills, pa.kit, pa.spm, pa.kd) == (
        a,
        True,
        30,
        "assault",
        450,
        6.0,
    )
    assert (pb.persona_id, pb.status, pb.won, pb.seconds, pb.spm) == (b, "left", None, 0, None)

    mine = await round_service.list_player_rounds(test_session, a, limit=1)
    assert [i.player.kills for i in mine.items] == [30]
    # 列表也带阵营，玩家对局页据此显示所在队伍的旗帜
    assert mine.items[0].round.team1_faction == detail.team1_faction
    rest = await round_service.list_player_rounds(test_session, a, before=mine.next_before)
    assert [i.player.kills for i in rest.items] == [20] and rest.next_before is None

    with pytest.raises(NotFoundError):
        await round_service.get_round(test_session, 12345)


async def test_tracker_caps_queries_and_prioritizes_leavers(monkeypatch) -> None:
    from app.services.bf1 import match_tracker

    monkeypatch.setattr(match_tracker, "MAX_QUERY_PER_TICK", 3)
    career, tr = Career(), MatchTracker()
    for p in range(1, 7):
        career.add(p)
    t0 = 1_800_000_000
    await tr.tick(_roster(p1=TEAM1, p2=TEAM1, p3=TEAM2), MAP, t0, career.fetch)
    # 4、5、6 进服，1 离开：离开的人先查，新进服的只查得下两个，剩下的下一轮补
    career.add(1, k=1, s=50)
    roster = _roster(p2=TEAM1, p3=TEAM2, p4=TEAM1, p5=TEAM2, p6=TEAM2)
    await tr.tick(roster, MAP, t0 + 60, career.fetch)
    stats_calls = [pids for pids, names in career.calls if len(names["player_statcategory"]) > 1]
    assert stats_calls[-1] == [1, 4, 5]
    await tr.tick(roster, MAP, t0 + 120, career.fetch)
    assert all(s.base is not None for s in tr.rounds[1].seats.values())


def _probe_calls(career: Career) -> list[list[int]]:
    return [pids for pids, names in career.calls if names == PROBE_NAMES]


async def test_tracker_probe_two_stages() -> None:
    career, tr = Career(), MatchTracker()
    for p in (1, 2, 3, 4):
        career.add(p)
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p2=TEAM1, p3=TEAM2, p4=TEAM2)
    await tr.tick(roster, MAP, t0, career.fetch)
    # 没结算：第一段 2 人都没变，不补查
    await tr.tick(roster, MAP, t0 + 60, career.fetch)
    assert _probe_calls(career) == [[1, 2]]
    # 只有 1 个人 +1：同一轮补查另外 2 人，4 人里 1 人不过半
    career.add(1, w=1, r=1)
    await tr.tick(roster, MAP, t0 + 120, career.fetch)
    assert _probe_calls(career)[1:] == [[1, 2], [3, 4]]
    assert tr.rounds[1].settle_seen_at is None
    # 正常结算：第一段 2 人都 +1 就够了
    career.settle(winners=[2, 3], losers=[4])
    career.add(1, l=1, r=1)
    await tr.tick(roster, MAP, t0 + 180, career.fetch)
    assert _probe_calls(career)[3:] == [[1, 2]]
    assert tr.rounds[1].settle_seen_at == t0 + 180


async def test_tracker_reuses_vector_after_hop_and_rechecks_lightly(monkeypatch) -> None:
    events: Counter[str] = Counter()
    monkeypatch.setattr(ea_metrics, "count_event", lambda name, n=1: events.update({name: n}))
    career, tr = Career(), MatchTracker()
    for p in (1, 2, 3):
        career.add(p)
    t0 = 1_800_000_000
    maps = {1: MAP[1], 2: MAP[1]}
    await tr.tick({1: {1: (TEAM1, "p1"), 2: (TEAM2, "p2")}}, maps, t0, career.fetch)
    # 1 中途退出（立刻写入），下一轮查到终值；再下一轮出现在 2 号服，3 从离线直接进 2 号服
    career.add(1, k=2, s=300)
    await tr.tick({1: {2: (TEAM2, "p2")}}, maps, t0 + 60, career.fetch)
    rosters = {1: {2: (TEAM2, "p2")}, 2: {1: (TEAM1, "p1"), 3: (TEAM2, "p3")}}
    await tr.tick(rosters, maps, t0 + 120, career.fetch)
    seat = tr.rounds[2].seats[1]
    assert (seat.hop, tr.rounds[2].seats[3].hop) == (True, False)
    assert (seat.base, seat.base_at) == (career.vec[1], t0 + 60)
    assert (events["join_hop"], events["join_fresh"], events["join_reused"]) == (1, 3, 1)
    # 1 进 2 号服没有再查基线
    assert events["want_join"] == 3
    # 1 带着之前那局迟到的胜负；复查只查局数胜负，变了的才在同一轮重查全量
    career.add(1, w=1, r=1)
    calls = len(career.calls)
    for t in range(t0 + 180, t0 + 121 + RECHECK_AFTER, 60):
        await tr.tick(rosters, maps, t, career.fetch)
    light = [pids for pids, names in career.calls[calls:] if names == RECHECK_NAMES]
    assert sorted(p for pids in light for p in pids) == [1, 2, 3]
    assert (events["recheck_changed_hop"], events["recheck_same_fresh"]) == (1, 2)
    assert events["want_recheck"] == 1 and events["recheck_light"] == 3
    assert tr.rounds[2].seats[1].base == career.vec[1]


async def test_tracker_does_not_reuse_vector_from_before_leaving() -> None:
    career, tr = Career(), MatchTracker()
    for p in (1, 2):
        career.add(p)
    t0 = 1_800_000_000
    maps = {1: MAP[1], 2: MAP[1]}
    await tr.tick({1: {1: (TEAM1, "p1"), 2: (TEAM2, "p2")}}, maps, t0, career.fetch)
    # 1 退出时写入，同一轮就出现在 2 号服：手上只有离开前的基线，不能拿来用
    career.add(1, k=5, s=900)
    rosters = {1: {2: (TEAM2, "p2")}, 2: {1: (TEAM1, "p1")}}
    await tr.tick(rosters, maps, t0 + 60, career.fetch)
    assert tr.rounds[2].seats[1].base == career.vec[1]


async def test_tracker_dump_and_load_continue_the_round() -> None:
    career, tr = Career(), MatchTracker()
    for p in (1, 2, 3, 4):
        career.add(p)
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p2=TEAM1, p3=TEAM2, p4=TEAM2)
    await tr.tick(roster, MAP, t0, career.fetch)
    await tr.tick(roster, MAP, t0 + 60, career.fetch)
    # 换进程：导出成 JSON 再导入，接着跟到结算
    restored = MatchTracker()
    restored.load(json.loads(json.dumps(tr.dump())))
    assert restored.dump() == tr.dump()
    base_calls = len(career.calls)
    career.settle(winners=[1, 2], losers=[3, 4])
    await restored.tick(roster, MAP, t0 + 120, career.fetch)
    [closed] = await restored.tick(roster, MAP, t0 + 180, career.fetch)
    assert closed.observed_start is False and closed.winner == 1
    assert {ln.pid: ln.delta[WINS] for ln in closed.lines} == {1: 1, 2: 1, 3: 0, 4: 0}
    # 不用重查基线：导入后只有探测和收尾的查询
    assert all(len(pids) <= 4 for pids, _ in career.calls[base_calls:])


async def test_save_and_restore_tracker_state(monkeypatch) -> None:
    store: dict[str, str] = {}

    class Redis:
        async def set(self, key: str, value: str, ex: int) -> None:
            store[key] = value

        async def getdel(self, key: str) -> str | None:
            return store.pop(key, None)

    async def fake_redis() -> Redis:
        return Redis()

    monkeypatch.setattr(round_service, "get_redis", fake_redis)
    career, tr = Career(), MatchTracker()
    career.add(1)
    now = int(datetime.now(UTC).timestamp())
    await tr.tick(_roster(p1=TEAM1), MAP, now - 30, career.fetch)
    await round_service.save_tracker_state(tracker=tr)
    fresh = MatchTracker()
    await round_service.restore_tracker_state(tracker=fresh)
    assert fresh.dump() == tr.dump() and not store
    # 太旧的状态不用
    tr.last_tick = now - 10_000
    await round_service.save_tracker_state(tracker=tr)
    stale = MatchTracker()
    await round_service.restore_tracker_state(tracker=stale)
    assert stale.rounds == {} and stale.last_tick is None
