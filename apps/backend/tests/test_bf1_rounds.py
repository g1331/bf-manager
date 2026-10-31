"""对局：单局战绩编码、生涯差分跟踪器，以及落库后的三种查询。"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from app.api.errors import NotFoundError
from app.core import ea_metrics
from app.domain.games.bf1 import round_awards as ra
from app.domain.games.bf1 import round_weapons as rw
from app.domain.games.bf1.blaze_catalog import catalog
from app.domain.games.bf1.blaze_stats import STAT
from app.domain.games.bf1.round_stats import (
    ACE_SQUAD,
    COMBAT,
    DEATHS,
    FINISHED,
    KILLS,
    KIT_BASE,
    KIT_RANKS,
    LEFT_EARLY,
    LOSSES,
    MODE_SCORES,
    MVP,
    OBJECTIVE,
    PROBE_NAMES,
    RANK,
    RECHECK_NAMES,
    RECORDS,
    RIBBONS,
    ROUND_STATS,
    ROUNDS,
    SC_AWARD,
    SCALE,
    SCORE,
    SCORE_PARTS,
    SKILL,
    SUSPECT,
    WINS,
    Entry,
    decode_entries,
    diff,
    encode_entry,
    pack_pids,
    same_core,
    to_vector,
    unpack_pids,
)
from app.models.bf1.game_instance import Bf1GameInstance
from app.models.bf1.rounds import Bf1PlayerRoundDay, Bf1Round
from app.services.bf1 import round_service
from app.services.bf1.match_tracker import (
    MISSING_RETRY,
    RECHECK_AFTER,
    ClosedRound,
    MatchTracker,
    RoundLine,
)
from app.services.bf1.server_roster_service import QUEUE, TEAM1, TEAM2
from sqlalchemy import select

N = len(ROUND_STATS)


def test_entry_codec_roundtrip_and_sparse() -> None:
    delta = [0] * N
    delta[KILLS], delta[DEATHS], delta[SCORE], delta[N - 1] = 23, 17, 5840, 1620
    blob = encode_entry(123456, 2, SUSPECT, delta) + encode_entry(7, 1, FINISHED, [0] * N)
    assert decode_entries(blob) == [
        (123456, 2, SUSPECT, {KILLS: 23, DEATHS: 17, SCORE: 5840, N - 1: 1620}, None, None, {}),
        (7, 1, FINISHED, {}, None, None, {}),
    ]
    # 3 字节 id + 1 字节队伍状态 + 1 字节个数 + 4 项（间隔与值共 2–4 字节）
    assert len(encode_entry(123456, 2, SUSPECT, delta)) <= 20
    # 武器载具接在核心后面；读到了但全是 0 的（空 dict）和没读到的（None）要分得开
    with_weapons = encode_entry(8, 2, LEFT_EARLY, delta, {0: 3, 1795: 600}) + encode_entry(
        9, 1, FINISHED, [0] * N, {}
    )
    assert decode_entries(with_weapons) == [
        (
            8,
            2,
            LEFT_EARLY,
            {KILLS: 23, DEATHS: 17, SCORE: 5840, N - 1: 1620},
            {0: 3, 1795: 600},
            None,
            {},
        ),
        (9, 1, FINISHED, {}, {}, None, {}),
    ]


def test_pids_pack_and_vector_diff() -> None:
    pids = [1005811915302, 1003517866915, 1601233727, 1003517866915]
    assert unpack_pids(pack_pids(pids)) == sorted(set(pids))
    assert len(pack_pids(pids)) < 8 * 3
    v = to_vector({"kills": 3.0, "c___kak_g": 1.6, "nonexistent": 9})
    assert (v[KILLS], v[6], len(v)) == (3, 2, N)
    assert diff([1, 2], [1, 1]) == [0, 1]
    assert diff([1, 0], [1, 1]) is None


def test_end_values_signed_skill_and_short_base() -> None:
    base = [100] * N
    end = list(base)
    end[KILLS] += 5
    end[SKILL] -= 37  # 技巧值降了 3.7
    end[RANK] += 1
    end[RECORDS["max_killstreak"]] += 4
    d = diff(end, base)
    assert d is not None
    # 等级、纪录记新值；技巧值记负的增量，不当成坏数据
    assert (d[KILLS], d[SKILL], d[RANK], d[RECORDS["max_killstreak"]]) == (5, -37, 101, 104)
    assert d[RECORDS["longest_headshot"]] == 0
    bad = list(end)
    bad[DEATHS] -= 1
    assert diff(bad, base) is None
    # 追加统计项之前查到的基线只有前 34 项：只减共有部分，新加的项这一局记 0
    short = base[:34]
    d = diff(end, short)
    assert d is not None and len(d) == N
    assert (d[KILLS], d[SKILL], d[RANK]) == (5, 0, 0)
    assert same_core(short, base) and not same_core(short, end)
    assert to_vector({"skill": 312.47})[SKILL] == 3125

    full = [0] * N
    full[KILLS], full[SKILL] = 5, -37
    [e] = decode_entries(encode_entry(9, 1, FINISHED, full, {3: 1}, {33: 1, 47: 2}, {12: 24}))
    assert (e.stats, e.weapons, e.awards, e.stars) == (
        {KILLS: 5, SKILL: -37},
        {3: 1},
        {33: 1, 47: 2},
        {12: 24},
    )
    # 读到了勋带但一个没拿（空 dict）和没读到（None）要分得开
    e1, e2 = decode_entries(
        encode_entry(1, 1, FINISHED, [0] * N, None, {}) + encode_entry(2, 1, FINISHED, [0] * N)
    )
    assert (e1.awards, e1.weapons, e2.awards) == ({}, None, None)


class Career:
    """假的 Blaze：按 pid 存生涯向量，fetch 按统计名返回。"""

    def __init__(self) -> None:
        self.vec: dict[int, list[int]] = {}
        # 核心以外的统计（武器载具、哨兵），没写的按 0
        self.extra: dict[int, dict[str, float]] = {}
        self.calls: list[tuple[list[int], dict[str, list[str]]]] = []
        self.fail = False
        self.fail_categories: set[str] = set()
        # (pid, 类别)：请求成功，但这一类没返回这个人
        self.missing: set[tuple[int, str]] = set()

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

    def use(self, pid: int, **stats: float) -> None:
        extra = self.extra.setdefault(pid, {})
        for name, v in stats.items():
            extra[name] = extra.get(name, 0.0) + v

    async def fetch(self, pids: list[int], names: dict[str, list[str]]) -> dict:
        if self.fail or names.keys() & self.fail_categories:
            raise RuntimeError("blaze down")
        self.calls.append((pids, names))
        core = {name: i for i, (_, name) in enumerate(ROUND_STATS)}
        return {
            p: {
                name: self.vec[p][core[name]] / SCALE.get(core[name], 1)
                if name in core
                else self.extra.get(p, {}).get(name, 0.0)
                for cat, ns in names.items()
                if (p, cat) not in self.missing
                for name in ns
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
            Bf1GameInstance(
                game_id=10, server_id=99, name="old", first_seen=now, last_seen=now - timedelta(1)
            ),
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
    # 重启前的局也指向这台服现在的 gameId，前端靠它跳到服务器详情
    assert [(r.game_id, r.server_game_id, r.server_name, r.player_count) for r in page.items] == [
        (11, 11, "mine", 2),
        (10, 11, "old", 1),
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
    # 没死过时 KD 就是击杀数，不再是 None（前端曾显示成 ∞）
    entry = Entry(1, 1, FINISHED, {KILLS: 9}, None, None, {})
    assert round_service._player(1, entry, None).kd == 9
    assert round_service._player(1, entry._replace(stats={}), None).kd == 0

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


async def test_tracker_backs_off_when_ea_has_no_data(monkeypatch) -> None:
    events: Counter[str] = Counter()
    monkeypatch.setattr(ea_metrics, "count_event", lambda name, n=1: events.update({name: n}))
    career, tr = Career(), MatchTracker()
    career.add(1)  # 3 在 EA 那边没有数据
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p3=TEAM2)
    await tr.tick(roster, MAP, t0, career.fetch)
    assert events["stats_missing"] == 1 and tr.rounds[1].seats[3].retry_at == t0 + MISSING_RETRY
    # 退避期间不再查他
    for t in range(t0 + 60, t0 + MISSING_RETRY, 60):
        await tr.tick(roster, MAP, t, career.fetch)
    assert all(3 not in pids for pids, _ in career.calls[1:])
    assert events["want_join"] == 2
    # 到点再查，这回有了
    career.add(3)
    await tr.tick(roster, MAP, t0 + MISSING_RETRY, career.fetch)
    assert tr.rounds[1].seats[3].base == career.vec[3]
    assert events["want_join"] == 3 and events["stats_missing"] == 1


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


def test_weapon_slots_cover_catalog_and_snapshot_codec() -> None:
    names = [name for cat, ns in rw.slots_by_category().items() for name in ns.values()]
    catalog_names = [
        n
        for kind in ("weapons", "vehicles")
        for e in catalog(kind).values()
        for n in e["stats"].values()
    ]
    # 目录里每个统计名都有且只有一个槽位
    assert sorted(names) == sorted(catalog_names) and len(set(names)) == len(names)
    assert set(rw.slots_by_category()) == {STAT, *rw.ALWAYS, *rw.GATES}
    # 每个有哨兵的类别都配了抽查间隔，加了新类别忘记配会在跟踪器里 KeyError
    from app.services.bf1 import match_tracker

    assert set(match_tracker.AUDIT_EVERY) == set(rw.GATES)
    full = rw.full_names()
    assert all(len(ns) == len(set(ns)) for ns in full.values())
    assert set(rw.slots_by_category()[STAT].values()) <= set(full[STAT])
    assert {n for _, n in rw.GATE_NAMES} <= {n for ns in full.values() for n in ns}

    blob = rw.pack([1, 2, 3], {5: 100, 1800: 7})
    assert rw.unpack(blob) == ([1, 2, 3], {5: 100, 1800: 7})
    later = rw.pack([1, 2, 4], {5: 130, 9: 2, 1800: 7})
    assert rw.diff(later, blob) == {5: 30, 9: 2}
    assert rw.diff(blob, later) is None
    kills_slot = 2 * len(rw.METRICS) + rw.KILLS_METRIC
    assert rw.kills({kills_slot: 4, kills_slot + 1: 600, 0: 2}) == 6
    # 战马的击杀已经记在骑乘时用的武器上，对账不重复加
    horse = rw.items().index("v:horse") * len(rw.METRICS) + rw.KILLS_METRIC
    assert rw.kills({kills_slot: 4, horse: 4}) == 4
    assert set(rw.items()) >= rw.SHARED_KILLS


def test_catalog_names_are_simplified() -> None:
    # EA 只给繁体，目录加载时转简体
    texts = [
        e[f]
        for kind in ("weapons", "vehicles")
        for e in catalog(kind).values()
        for f in ("name", "category")
        if e.get(f)
    ]
    assert not [t for t in texts if set(t) & set("槍彈擊戰馬輕衝機車")]
    assert catalog("vehicles")["horse"]["name"] == "战马"


def test_round_weapons_flag_shared_kills() -> None:
    horse = rw.items().index("v:horse") * len(rw.METRICS)
    gun, _ = _slot("player_weapons1")
    weapons = round_service._weapons({horse + rw.KILLS_METRIC: 3, gun: 3})
    assert weapons is not None
    assert {(w.name, w.shared_kills) for w in weapons} == {
        ("战马", True),
        (rw_entry(gun)["name"], False),
    }


def _slot(cat: str, metric: str = "kills", nth: int = 0) -> tuple[int, str]:
    """某类别里第 nth 个有该指标的槽位和统计名"""
    found = [
        (slot, name)
        for slot, name in sorted(rw.slots_by_category()[cat].items())
        if rw.METRICS[slot % len(rw.METRICS)] == metric
    ]
    return found[nth]


def rw_entry(slot: int) -> dict:
    key, _ = rw.slot_item(slot)
    prefix, code = key.split(":", 1)
    return catalog("weapons" if prefix == "w" else "vehicles")[code]


def _gate(cat: str, i: int = 0) -> str:
    return rw.GATES[cat][i][1]


class MemoryStore:
    def __init__(self) -> None:
        self.rows: dict[int, tuple[list[int], bytes, int]] = {}
        self.awards: dict[int, bytes] = {}

    async def load(self, pids: list[int]) -> dict[int, tuple[list[int], bytes, int]]:
        return {p: self.rows[p] for p in pids if p in self.rows}

    async def save(self, snapshots: dict[int, tuple[list[int], bytes, int]]) -> None:
        self.rows.update(snapshots)

    async def load_awards(self, pids: list[int]) -> dict[int, tuple[bytes, int]]:
        return {p: (self.awards[p], self.rows[p][2]) for p in pids if p in self.awards}

    async def save_awards(self, snapshots: dict[int, bytes]) -> None:
        self.awards.update((p, b) for p, b in snapshots.items() if p in self.rows)


def _weapon_reads(career: Career, since: int = 0) -> dict[str, list[int]]:
    """各武器类别被读过的人"""
    out: dict[str, list[int]] = {}
    for pids, names in career.calls[since:]:
        [(cat, _)] = names.items() if len(names) == 1 else [(None, None)]
        if cat in (*rw.ALWAYS, *rw.GATES):
            out.setdefault(cat, []).extend(pids)
    return out


def _events(monkeypatch) -> Counter[str]:
    events: Counter[str] = Counter()
    monkeypatch.setattr(ea_metrics, "count_event", lambda name, n=1: events.update({name: n}))
    return events


async def test_tracker_records_weapons_with_two_stage_reads(monkeypatch) -> None:
    from app.services.bf1 import match_tracker

    monkeypatch.setattr(match_tracker, "AUDIT_EVERY", dict.fromkeys(rw.GATES, 10**12))  # 不抽查
    events = _events(monkeypatch)
    career, tr, store = Career(), MatchTracker(), MemoryStore()
    for p in (1, 2, 3, 4):
        career.add(p)
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p2=TEAM1, p3=TEAM2, p4=TEAM2)
    await tr.tick(roster, MAP, t0, career.fetch, store)
    # 没有任何旧快照：7 个武器类别都读，读完存起来
    assert _weapon_reads(career) == {cat: [1, 2, 3, 4] for cat in (*rw.ALWAYS, *rw.GATES)}
    assert sorted(store.rows) == [1, 2, 3, 4]
    assert all(s.base_w is not None for s in tr.rounds[1].seats.values())

    mg, mg_name = _slot("player_weapons1")
    rifle, rifle_name = _slot("player_weapons2")
    bomber, bomber_name = _slot("player_statcategory4", "seconds")
    tank, tank_name = _slot(STAT, "seconds")
    career.use(1, **{mg_name: 10, bomber_name: 100, _gate("player_statcategory4"): 100})
    career.use(2, **{rifle_name: 10, tank_name: 50})
    career.use(3, **{mg_name: 3})
    career.settle(winners=[1, 2], losers=[3, 4])
    calls = len(career.calls)
    await tr.tick(roster, MAP, t0 + 60, career.fetch, store)
    [closed] = await tr.tick(roster, MAP, t0 + 120, career.fetch, store)

    # 核心都变了：武器 1–5 类四人都读；轰炸机哨兵只有 1 变了，第 4 类只读他；第 3 类谁都不读
    reads = _weapon_reads(career, calls)
    assert all(sorted(reads[cat]) == [1, 2, 3, 4] for cat in rw.ALWAYS)
    assert reads["player_statcategory4"] == [1] and "player_statcategory3" not in reads
    weapons = {ln.pid: ln.weapons for ln in closed.lines}
    assert weapons == {1: {mg: 10, bomber: 100}, 2: {rifle: 10, tank: 50}, 3: {mg: 3}, 4: {}}
    # 对账：1、2 的武器击杀等于核心击杀；3、4 的击杀有一部分不在目录里
    assert (events["weapons_kills_match"], events["weapons_kills_diff"]) == (2, 2)
    assert (events["weapons_gate_read_4"], events["weapons_gate_skip_4"]) == (1, 3)
    assert events["weapons_gate_skip_3"] == 4
    # 下一局的基线带着武器载具快照，导出导入不丢
    assert all(s.base_w is not None for s in tr.rounds[1].seats.values())
    restored = MatchTracker()
    restored.load(json.loads(json.dumps(tr.dump())))
    assert restored.dump() == tr.dump()
    assert restored.rounds[1].seats[1].base_w == tr.rounds[1].seats[1].base_w


async def test_tracker_reuses_stored_weapons_and_audits_gates(monkeypatch) -> None:
    from app.services.bf1 import match_tracker

    monkeypatch.setattr(match_tracker, "AUDIT_EVERY", dict.fromkeys(rw.GATES, 10**12))
    events = _events(monkeypatch)
    career, store = Career(), MemoryStore()
    for p in (1, 2):
        career.add(p)
    t0 = 1_800_000_000
    await MatchTracker().tick(_roster(p1=TEAM1, p2=TEAM2), MAP, t0, career.fetch, store)
    # 一小时后换了进程：1 期间没打过，2 在别处打过一局
    mg, mg_name = _slot("player_weapons1")
    career.add(2, k=3, s=400)
    career.use(2, **{mg_name: 3})
    tr = MatchTracker()
    calls = len(career.calls)
    t = t0 + 3600
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2), MAP, t, career.fetch, store)
    reads = _weapon_reads(career, calls)
    assert reads == {cat: [2] for cat in rw.ALWAYS}  # 1 全部沿用；2 的冷门类别哨兵没变也沿用
    assert (events["join_core_same"], events["join_core_changed"]) == (1, 1)
    assert (events["weapons_store_hit"], events["weapons_reused"]) == (2, 1)
    assert tr.rounds[1].seats[1].base_w == store.rows[1][1]
    assert rw.unpack(tr.rounds[1].seats[2].base_w)[1][mg] == 3

    # 抽查：2 开了飞船但哨兵都没动（哨兵漏了），抽中照读时能发现并用上真实值
    monkeypatch.setattr(match_tracker, "AUDIT_EVERY", dict.fromkeys(rw.GATES, 1))
    airship, airship_name = _slot("player_statcategory3", "seconds", 1)
    base_w = tr.rounds[1].seats[2].base_w
    career.add(2, k=1, s=100)
    career.use(2, **{mg_name: 1, airship_name: 30})
    await tr.tick(_roster(p1=TEAM1), MAP, t + 60, career.fetch, store)
    seat = tr.rounds[1].seats[2]
    assert seat.left and rw.diff(seat.end_w, base_w) == {mg: 1, airship: 30}
    assert (events["weapons_audit_miss_3"], events["weapons_audit_ok_4"]) == (1, 1)


async def test_tracker_weapons_failures_and_cap(monkeypatch) -> None:
    from app.services.bf1 import match_tracker

    events = _events(monkeypatch)
    career, tr, store = Career(), MatchTracker(), MemoryStore()
    for p in (1, 2, 3):
        career.add(p)
    t0 = 1_800_000_000
    # 一个武器类别读失败：这一轮的人没有武器载具快照，核心照常
    career.fail_categories = {"player_weapons3"}
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2), MAP, t0, career.fetch, store)
    seats = tr.rounds[1].seats
    assert all(s.base is not None and s.base_w is None for s in seats.values())
    assert events["weapons_failed"] == 2 and store.rows == {}
    # 这局的行没有武器载具数据（不是「没用武器」）
    career.fail_categories = set()
    career.settle(winners=[1], losers=[2])
    await tr.tick(_roster(p1=TEAM1, p2=TEAM2), MAP, t0 + 60, career.fetch, store)
    [closed] = await tr.tick(_roster(p1=TEAM1, p2=TEAM2), MAP, t0 + 120, career.fetch, store)
    assert [ln.weapons for ln in closed.lines] == [None, None]
    assert all(s.base_w is not None for s in tr.rounds[1].seats.values())

    # 超出每轮上限：离开的人优先，新进服的这一局没有武器载具数据
    monkeypatch.setattr(match_tracker, "MAX_WEAPONS_PER_TICK", 1)
    career.add(1, k=2, s=300)
    await tr.tick(_roster(p2=TEAM2, p3=TEAM1), MAP, t0 + 180, career.fetch, store)
    seats = tr.rounds[1].seats
    assert seats[1].end_w is not None and seats[3].base is not None and seats[3].base_w is None
    assert events["weapons_skipped"] == 1


async def test_snapshot_store_and_weapon_entries(test_session) -> None:
    store = round_service.SnapshotStore(test_session)
    now = int(datetime.now(UTC).timestamp())
    await store.save({1: ([1, 0, 300], b"\x01\x02", now - 60), 2: ([5], b"", now - 60)})
    await store.save({1: ([2, 0, 300], b"\x03", now)})
    assert await store.load([1, 2, 3]) == {1: ([2, 0, 300], b"\x03", now), 2: ([5], b"", now - 60)}
    # 过期清理也清快照
    await round_service.purge_expired(
        test_session, datetime.fromtimestamp(now, UTC) + round_service.SNAPSHOT_RETENTION
    )
    assert await store.load([1, 2]) == {1: ([2, 0, 300], b"\x03", now)}
    # 勋带只更新已有的快照行
    await store.save_awards({1: b"\x07", 99: b"\x08"})
    assert await store.load_awards([1, 2, 99]) == {1: (b"\x07", now)}

    a, b = 1005811915302, 1003517866915
    mg, _ = _slot("player_weapons1")
    mg_seconds, _ = _slot("player_weapons1", "seconds")
    tank = next(
        slot
        for slot in sorted(rw.slots_by_category()[STAT])
        if rw.slot_item(slot)[0].startswith("v:") and rw.slot_item(slot)[1] == "kills"
    )
    lines = [
        RoundLine(a, 1, FINISHED, _delta(3, win=True), {mg: 1, mg_seconds: 300, tank: 2}),
        RoundLine(b, 2, FINISHED, _delta(1, win=False)),
    ]
    await round_service.save_rounds(test_session, [_closed(10, now, lines)])
    row = await test_session.get(Bf1PlayerRoundDay, (a, datetime.fromtimestamp(now, UTC).date()))
    [e] = decode_entries(row.data)
    rid = e.round_id
    assert e.stats[KILLS] == 3 and e.weapons == {mg: 1, mg_seconds: 300, tank: 2}
    # 接口按条目合并：载具击杀多排在前；没有数据的人是 None
    detail = await round_service.get_round(test_session, rid)
    players = {p.persona_id: p for p in detail.players}
    first, second = players[a].weapons
    assert (first.kind, first.kills, first.name) == ("vehicle", 2, rw_entry(tank)["name"])
    assert (second.kind, second.kills, second.seconds) == ("weapon", 1, 300)
    assert second.image and second.image.startswith("http")
    assert players[b].weapons is None


def _award_reads(career: Career, since: int = 0) -> list[int]:
    """读过勋带类别的人"""
    return sorted(
        p for pids, names in career.calls[since:] if names.keys() == ra.names().keys() for p in pids
    )


async def test_tracker_records_awards_mvp_and_stars(monkeypatch) -> None:
    from app.services.bf1 import match_tracker

    monkeypatch.setattr(match_tracker, "AWARDS_AUDIT_EVERY", 10**12)  # 不抽查
    events = _events(monkeypatch)
    career, tr, store = Career(), MatchTracker(), MemoryStore()
    for p in (1, 2):
        career.add(p)
    mg, mg_name = _slot("player_weapons1")
    career.use(1, **{mg_name: 95, "r33_00": 4})
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p2=TEAM2)
    await tr.tick(roster, MAP, t0, career.fetch, store)
    # 没有旧快照：两人都读勋带，存进快照行
    assert _award_reads(career) == [1, 2]
    assert sorted(store.awards) == [1, 2]
    assert rw.unpack(tr.rounds[1].seats[1].base_a)[1] == {33: 4}

    # 结算：1 是 MVP、升了一级，拿了 2 次 r33 和 1 次 r01，机枪击杀跨过 100；
    # 2 的勋带门控没变，沿用上次的勋带，不读
    career.settle(winners=[1], losers=[2])
    v = career.vec[1]
    v[MVP] += 1
    v[RIBBONS] += 3
    v[SC_AWARD] += 1500
    v[RANK] += 1
    career.use(1, **{mg_name: 10, "r33_00": 2, "r01_00": 1})
    calls = len(career.calls)
    await tr.tick(roster, MAP, t0 + 60, career.fetch, store)
    [closed] = await tr.tick(roster, MAP, t0 + 120, career.fetch, store)
    assert _award_reads(career, calls) == [1]
    assert events["awards_reused"] == 1
    lines = {ln.pid: ln for ln in closed.lines}
    assert (lines[1].awards, lines[2].awards) == ({33: 2, 1: 1}, {})
    assert (lines[1].delta[MVP], lines[1].delta[RANK], lines[2].delta[RANK]) == (1, 101, 0)
    assert lines[1].stars == {mg // len(rw.METRICS): 1} and lines[2].stars == {}
    # 下一局的基线带着勋带快照，导出导入不丢
    restored = MatchTracker()
    restored.load(json.loads(json.dumps(tr.dump())))
    assert restored.dump() == tr.dump()
    assert restored.rounds[1].seats[1].base_a == tr.rounds[1].seats[1].base_a


async def test_tracker_awards_failure_does_not_touch_weapons(monkeypatch) -> None:
    events = _events(monkeypatch)
    career, tr, store = Career(), MatchTracker(), MemoryStore()
    for p in (1, 2):
        career.add(p)
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p2=TEAM2)
    career.fail_categories = {"player_awards4"}
    await tr.tick(roster, MAP, t0, career.fetch, store)
    seats = tr.rounds[1].seats
    assert all(s.base_w is not None and s.base_a is None for s in seats.values())
    assert events["awards_failed"] == 2 and store.awards == {}
    career.fail_categories = set()
    career.settle(winners=[1], losers=[2])
    await tr.tick(roster, MAP, t0 + 60, career.fetch, store)
    [closed] = await tr.tick(roster, MAP, t0 + 120, career.fetch, store)
    assert [(ln.weapons, ln.awards) for ln in closed.lines] == [({}, None), ({}, None)]

    # 请求成功但一个勋带类别没返回某人：不能把缺的当成 0 存下来，这个人这轮没有勋带
    base_a = tr.rounds[1].seats[1].base_a
    career.use(1, r46_00=2)
    career.vec[1][RIBBONS] += 2
    career.missing = {(1, "player_awards4")}
    career.add(1, k=1, s=100)
    await tr.tick(_roster(p2=TEAM2), MAP, t0 + 180, career.fetch, store)
    seat = tr.rounds[1].seats[1]
    assert seat.left and seat.end is not None and seat.end_a is None
    assert store.awards[1] == base_a and events["awards_failed"] == 3


async def test_tracker_survives_state_from_before_the_upgrade(monkeypatch) -> None:
    events = _events(monkeypatch)
    career, tr, store = Career(), MatchTracker(), MemoryStore()
    for p in (1, 2):
        career.add(p)
    t0 = 1_800_000_000
    roster = _roster(p1=TEAM1, p2=TEAM2)
    await tr.tick(roster, MAP, t0, career.fetch, store)
    # 升级前导出的状态和存的快照：核心向量只有 34 项，没有勋带
    old = 34
    data = tr.dump()
    for seat in data["rounds"]["1"]["seats"].values():
        seat["base"] = seat["base"][:old]
        del seat["base_a"], seat["end_a"]
    data["recent"] = {p: [v[0][:old], v[1], v[2]] for p, v in data["recent"].items()}
    store.rows = {p: (vec[:old], blob, at) for p, (vec, blob, at) in store.rows.items()}
    store.awards = {}

    # 换了进程、生涯没变：旧快照的武器照常沿用
    fresh = MatchTracker()
    await fresh.tick(roster, MAP, t0 + 3600, career.fetch, store)
    assert events["weapons_reused"] == 2 and events["join_core_same"] == 2

    # 跨部署接着跟的这一局能正常收尾，新加的项记 0、没有勋带
    restored = MatchTracker()
    restored.load(json.loads(json.dumps(data)))
    career.settle(winners=[1], losers=[2])
    career.vec[1][MVP] += 1
    await restored.tick(roster, MAP, t0 + 60, career.fetch, store)
    [closed] = await restored.tick(roster, MAP, t0 + 120, career.fetch, store)
    lines = {ln.pid: ln for ln in closed.lines}
    assert (lines[1].status, lines[1].delta[KILLS], lines[1].delta[MVP]) == (FINISHED, 10, 0)
    assert lines[1].awards is None and lines[1].weapons == {}


async def test_left_player_end_from_before_the_upgrade_still_saves(test_session) -> None:
    career, tr, store = Career(), MatchTracker(), MemoryStore()
    for p in (1, 2, 3):
        career.add(p)
    t0 = int(datetime.now(UTC).timestamp()) - 600
    await tr.tick(_roster(p1=TEAM1, p2=TEAM1, p3=TEAM2), MAP, t0, career.fetch, store)
    # 2 打完结算就走了，离开时的终值已查到；整服的结算要下一轮才收尾
    career.settle(winners=[1, 2], losers=[3])
    await tr.tick(_roster(p1=TEAM1, p3=TEAM2), MAP, t0 + 60, career.fetch, store)
    assert tr.rounds[1].seats[2].end is not None and tr.rounds[1].settle_seen_at is not None
    # 这时停机升级：导出的基线和终值都只有 34 项
    data = tr.dump()
    for seat in data["rounds"]["1"]["seats"].values():
        seat["base"] = seat["base"][:34]
        if seat["end"] is not None:
            seat["end"] = seat["end"][:34]
    restored = MatchTracker()
    restored.load(json.loads(json.dumps(data)))
    [closed] = await restored.tick(_roster(p1=TEAM1, p3=TEAM2), MAP, t0 + 120, career.fetch, store)
    lines = {ln.pid: ln for ln in closed.lines}
    assert (lines[2].status, lines[2].delta[KILLS], len(lines[2].delta)) == (FINISHED, 10, N)
    assert await round_service.save_rounds(test_session, [closed]) == 1


async def test_round_detail_honors_and_score_parts(test_session) -> None:
    now = int(datetime.now(UTC).timestamp())
    a, b = 1005811915302, 1003517866915
    d = _delta(30, win=True)  # 总分 9000，在场 1200 秒
    d[MVP] = d[ACE_SQUAD] = 1
    for k, v in {"general": 3000, "team": 500, "squad": 800, "award": 1500, "bonus": 2000}.items():
        d[SCORE_PARTS[k]] = v
    d[MODE_SCORES[0]] = 1000
    d[OBJECTIVE["flag_captures"]], d[COMBAT["headshots"]] = 3, 7
    d[SKILL], d[RANK], d[RECORDS["longest_headshot"]] = -37, 88, 312
    d[KIT_RANKS["medic"]] = 1
    mg, _ = _slot("player_weapons1")
    lines = [
        RoundLine(a, 1, FINISHED, d, {mg: 30}, {33: 2, 1: 1}, {mg // len(rw.METRICS): 24}),
        RoundLine(b, 2, FINISHED, _delta(1, win=False)),
    ]
    await round_service.save_rounds(test_session, [_closed(10, now, lines)])
    [rid] = (await test_session.scalars(select(Bf1Round.id))).all()
    detail = await round_service.get_round(test_session, rid)
    assert (detail.mvp_pid, detail.ace_squad_pids) == (a, [a])
    players = {p.persona_id: p for p in detail.players}
    pa, pb = players[a], players[b]
    # 计分板口径：总分减去勋带勋章奖励和结算奖励；SPM 按它算
    assert (pa.score, pa.battle_score, pa.spm) == (9000, 5500, 275)
    assert pa.score_parts is not None
    assert (pa.score_parts.objective, pa.score_parts.other) == (1000, 200)
    assert [(r.code, r.count) for r in pa.ribbons or []] == [("r33", 2), ("r01", 1)]
    assert (pa.objective, pa.combat) == ({"flag_captures": 3}, {"headshots": 7})
    assert (pa.rank_to, pa.skill_delta, pa.records, pa.kit_ranks) == (
        88,
        -3.7,
        {"longest_headshot": 312},
        ["medic"],
    )
    [star] = pa.stars
    assert (star.kind, star.name, star.stars) == ("weapon", rw_entry(mg)["name"], 24)
    assert pa.career is None  # 没有快照

    # 快照晚于这一局结束：先减掉这一局，得到这一局之前的生涯
    before = [0] * N
    before[KILLS], before[DEATHS], before[SCORE], before[KIT_BASE + 2] = 1000, 500, 600000, 36000
    before[SCORE_PARTS["bonus"]], before[SCORE_PARTS["award"]] = 100000, 50000
    before[COMBAT["hits"]], before[COMBAT["shots"]], before[COMBAT["headshots"]] = 3000, 12000, 150
    before[SKILL], before[RANK], before[RECORDS["longest_headshot"]] = 3000, 87, 300
    snap_vec = [x + y for x, y in zip(before, d, strict=True)]
    mg_slots = {m: mg - rw.KILLS_METRIC + rw.METRICS.index(m) for m in rw.METRICS}
    blob = rw.pack(
        [],
        {
            mg_slots["kills"]: 230,
            mg_slots["seconds"]: 6000,
            mg_slots["hits"]: 400,
            mg_slots["shots"]: 1600,
        },
    )
    await round_service.SnapshotStore(test_session).save({a: (snap_vec, blob, now + 60)})
    pa = {p.persona_id: p for p in (await round_service.get_round(test_session, rid)).players}[a]
    assert pa.career is not None
    assert (pa.career.kd, pa.career.kpm, pa.career.spm) == (2.0, 1.6667, 750)
    assert (pa.career.accuracy, pa.career.headshot_rate) == (0.25, 0.15)
    # 加上这一局之后：1030 杀 / 505 死，37200 秒，计分板口径得分 450000 + 5500
    after = pa.career_after
    assert after is not None
    assert (after.kd, after.kpm, after.spm) == (
        round(1030 / 505, 4),
        round(1030 * 60 / 37200, 4),
        round(455500 * 60 / 37200, 2),
    )
    assert after.headshot_rate == round(157 / 1030, 6)
    [w] = pa.weapons or []
    assert (w.career_accuracy, w.career_kpm, w.career_headshot_rate) == (0.25, 2.0, 0.0)
    # 升级前存的短快照：没有的项给空
    await round_service.SnapshotStore(test_session).save({a: (snap_vec[:34], blob, now - 60)})
    pa = {p.persona_id: p for p in (await round_service.get_round(test_session, rid)).players}[a]
    assert pa.career is not None
    assert (pa.career.kd, pa.career.spm, pa.career.accuracy) == (round(1030 / 505, 4), None, None)
    assert pa.career_after is not None and pa.career_after.spm is None

    # 没有新统计的条目（上线前的）维持原口径
    assert (pb.battle_score, pb.score_parts, pb.ribbons, pb.mvp, pb.spm) == (
        None,
        None,
        None,
        False,
        15,
    )


def _snap_entry(status: int, *, extended: bool) -> tuple[Entry, list[int]]:
    """这一局 20 杀 5 死、得分 6000、在场 600 秒；局前生涯 100 杀 50 死、得分 60000、6000 秒"""
    d = _delta(20, win=None, seconds=600)
    d[SCORE] = 6000
    if extended:
        d[COMBAT["shots"]], d[COMBAT["hits"]], d[COMBAT["headshots"]] = 200, 50, 4
        d[SCORE_PARTS["general"]] = 6000
    before = [0] * N
    before[KILLS], before[DEATHS], before[SCORE], before[KIT_BASE + 2] = 100, 50, 60000, 6000
    before[COMBAT["shots"]], before[COMBAT["hits"]], before[COMBAT["headshots"]] = 1000, 200, 20
    stats = {i: v for i, v in enumerate(d) if v}
    return Entry(1, 1, status, stats, None, None, {}), before


def test_round_career_snapshot_timing() -> None:
    blob = rw.pack([], {})
    span = (1000, 2000)
    # 中途退出的人：局中退出后读的终值已含这一局，要先减掉
    e, before = _snap_entry(LEFT_EARLY, extended=True)
    end = [x + e.stats.get(i, 0) for i, x in enumerate(before)]
    p = round_service._player(1, e, None, (end, blob, 1500), span)
    assert p.career is not None and p.career_after is not None
    assert (p.career.kd, p.career_after.kd) == (2.0, round(120 / 55, 4))
    # 打到结算的人：局中的快照只会是进服基线，不含这一局
    e, before = _snap_entry(FINISHED, extended=True)
    p = round_service._player(1, e, None, (before, blob, 1500), span)
    assert p.career is not None and (p.career.kd, p.career.accuracy) == (2.0, 0.2)
    # 开局前读的快照不含；结束后读的含
    assert round_service._player(1, e, None, (before, blob, 900), span).career.kd == 2.0  # type: ignore[union-attr]
    end = [x + e.stats.get(i, 0) for i, x in enumerate(before)]
    assert round_service._player(1, e, None, (end, blob, 2100), span).career.kd == 2.0  # type: ignore[union-attr]
    # 存疑的条目分不清快照含不含这一局，不比
    e, before = _snap_entry(SUSPECT, extended=True)
    assert round_service._player(1, e, None, (before, blob, 1500), span).career is None


def test_round_career_without_extended_stats() -> None:
    blob = rw.pack([], {})
    e, before = _snap_entry(FINISHED, extended=False)
    end = [x + e.stats.get(i, 0) for i, x in enumerate(before)]
    end[SCORE_PARTS["bonus"]] = 9000  # 新版快照里的奖励，这一局有多少不知道
    p = round_service._player(1, e, None, (end, blob, 2100), (1000, 2000))
    # 旧条目没有战斗、目标统计：给空，不是「全是 0」
    assert (p.combat, p.objective, p.battle_score) == (None, None, None)
    assert p.career is not None and p.career_after is not None
    # 击杀、死亡照常；命中、爆头、SPM 要减掉 / 加上这一局未知的增量，给空
    assert p.career.kd == 2.0
    assert (p.career.accuracy, p.career.headshot_rate, p.career.spm) == (None, None, None)
    assert (p.career_after.accuracy, p.career_after.headshot_rate, p.career_after.spm) == (
        None,
        None,
        None,
    )
    # 快照在这一局之前：之前的值完整，之后的未知项给空
    p = round_service._player(1, e, None, (before, blob, 900), (1000, 2000))
    assert p.career is not None and p.career_after is not None
    assert (p.career.accuracy, p.career_after.accuracy) == (0.2, None)
