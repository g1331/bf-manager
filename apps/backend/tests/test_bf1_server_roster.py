"""服务器快照：名单事件编解码、快照名单提取，以及多轮差分写入后的读取。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app.api.errors import NotFoundError
from app.models.bf1.server_roster import Bf1ServerPlayerDay
from app.schemas.bf1.server import ServerSummary
from app.services.bf1 import server_player_count_service as spc
from app.services.bf1.server_roster_service import (
    LEFT,
    QUEUE,
    SPECTATOR,
    TEAM1,
    TEAM2,
    RosterTracker,
    decode_events,
    encode_event,
    extract_rosters,
    tally_playtime,
    tally_visits,
)
from sqlalchemy import func, select


def test_event_codec_roundtrip() -> None:
    events = [(0, TEAM1), (86399, TEAM2), (43210, QUEUE), (1, 0), (7, SPECTATOR)]
    packed = "".join(encode_event(sec, state) for sec, state in events)
    assert len(packed) == 4 * len(events)
    assert decode_events(packed) == events


def _p(pid: int, tidx: int, *, role: str = "soldier") -> dict:
    return {"PID": pid, "NAME": f"p{pid}", "TIDX": tidx, "ROLE": role, "HNET": "secret"}


def test_extract_rosters_includes_official_without_private_fields() -> None:
    updates = [
        {"GAM": {"GID": 1, "ATTR": {"servertype": "OFFICIAL"}, "ROST": [_p(9, 0)]}},
        {
            "GAM": {
                "GID": 2,
                "ATTR": {"servertype": "RANKED"},
                "ROST": [_p(1, 0), _p(2, 1), _p(3, 65535, role=""), _p(4, 65535)],
            }
        },
        {"GID": 3, "ATTR": {}},
    ]
    rosters = extract_rosters(updates)
    assert rosters == {
        1: {9: (TEAM1, "p9")},
        2: {
            1: (TEAM1, "p1"),
            2: (TEAM2, "p2"),
            # 观战者 ROLE 为空，排队者 ROLE 为 soldier，两者 TIDX 都是 65535
            3: (SPECTATOR, "p3"),
            4: (QUEUE, "p4"),
        },
        3: {},
    }
    assert "secret" not in str(rosters)


def _summary(gid: int, players: int) -> ServerSummary:
    return ServerSummary(
        server_id=0, game_id=gid, name="mine", player_count=players, map_name="MP_Amiens"
    )


class _Clock(datetime):
    current: datetime

    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return cls.current


async def _round(test_session, at: datetime, roster: dict[int, int] | None) -> None:
    _Clock.current = at
    rosters = None if roster is None else {1: {pid: (s, f"p{pid}") for pid, s in roster.items()}}
    await spc.record_player_counts(test_session, [_summary(1, len(roster or {}))], rosters=rosters)


def _view(snapshot) -> dict[int, tuple[str, str | None]]:
    return {p.persona_id: (p.slot, p.change) for p in snapshot.roster}


async def test_rounds_record_changes_and_read_back(
    test_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spc, "datetime", _Clock)
    monkeypatch.setattr(spc, "roster_tracker", RosterTracker())
    # 时间放在库里数据的保留期内，从 UTC 23:58 开始跨过零点
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    t0 = today - timedelta(minutes=2)
    t1, t2 = t0 + timedelta(minutes=1), t0 + timedelta(minutes=2)
    a, b, c, d = 101, 102, 103, 104

    await _round(test_session, t0, {a: TEAM1, b: QUEUE})
    await _round(test_session, t1, {a: TEAM2, b: TEAM1, c: TEAM1})
    # 模拟重启：新的 tracker 从库里重建上一轮名单
    monkeypatch.setattr(spc, "roster_tracker", RosterTracker())
    await _round(test_session, t2, {b: TEAM1, c: TEAM1})
    # 快照失败回退 searchServers 的一轮：只有人数，没有名单
    await _round(test_session, t2 + timedelta(minutes=3), None)
    # 距上一轮有名单的已超过断档阈值：b、c 记为离开，但不算进这一轮的退出
    t3 = t2 + timedelta(minutes=10)
    await _round(test_session, t3, {d: TEAM2})

    page = await spc.list_roster_points(test_session, 1)
    ts = [int(x.timestamp()) for x in (t0, t1, t2, t3)]
    assert [(p.ts, p.joined, p.left) for p in page.items] == [
        (ts[3], 1, 0),
        (ts[2], 0, 1),
        (ts[1], 1, 0),
        (ts[0], 2, 0),
    ]

    snap = await spc.get_roster_snapshot(test_session, 1, ts[0])
    assert _view(snap) == {a: ("team1", "joined"), b: ("queue", "joined")}
    # 阵营按当时地图查：亚眠 Team1 德意志帝国、Team2 大英帝国
    assert (snap.team1_faction, snap.team2_faction) == ("德意志帝国", "大英帝国")
    snap = await spc.get_roster_snapshot(test_session, 1, ts[1])
    assert _view(snap) == {
        a: ("team2", "switched"),
        b: ("team1", "seated"),
        c: ("team1", "joined"),
    }
    assert {p.name for p in snap.roster} == {"p101", "p102", "p103"}
    # 零点后第一轮：跨天延续的人没有变化，离开的人带着离开前的位置
    snap = await spc.get_roster_snapshot(test_session, 1, ts[2])
    assert _view(snap) == {a: ("team2", "left"), b: ("team1", None), c: ("team1", None)}
    snap = await spc.get_roster_snapshot(test_session, 1, ts[3])
    assert _view(snap) == {d: ("team2", "joined")}

    # 每人每服每天一行：换队不新增行，前一天 3 人，当天 a、b、c 延续加 d
    rows = await test_session.execute(
        select(Bf1ServerPlayerDay.day, func.count()).group_by(Bf1ServerPlayerDay.day)
    )
    assert sorted(n for _, n in rows) == [3, 4]

    with pytest.raises(NotFoundError):
        await spc.get_roster_snapshot(test_session, 1, int((t2 + timedelta(minutes=3)).timestamp()))


async def test_spectator_entering_team_is_seated(
    test_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spc, "datetime", _Clock)
    monkeypatch.setattr(spc, "roster_tracker", RosterTracker())
    t0 = datetime.now(UTC) - timedelta(hours=1)
    t1 = t0 + timedelta(minutes=1)
    a, b = 301, 302
    await _round(test_session, t0, {a: SPECTATOR, b: TEAM1})
    await _round(test_session, t1, {a: TEAM2, b: SPECTATOR})

    snap = await spc.get_roster_snapshot(test_session, 1, int(t1.timestamp()))
    # 观战上场算进场；在队的人去观战仍是换队
    assert _view(snap) == {a: ("team2", "seated"), b: ("spectator", "switched")}


async def test_roster_page_paginates(test_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spc, "datetime", _Clock)
    monkeypatch.setattr(spc, "roster_tracker", RosterTracker())
    start = datetime.now(UTC) - timedelta(hours=1)
    for i in range(5):
        await _round(test_session, start + timedelta(minutes=i), {1: TEAM1, 2 + i: TEAM2})

    first = await spc.list_roster_points(test_session, 1, limit=3)
    assert [p.joined for p in first.items] == [1, 1, 1]
    assert first.next_before == first.items[-1].ts
    rest = await spc.list_roster_points(test_session, 1, before=first.next_before, limit=3)
    assert [p.joined for p in rest.items] == [1, 2]
    assert rest.items[-1].ts == int(start.timestamp())


def test_tally_playtime_counts_team_time_joins_and_clips() -> None:
    day = date(2026, 10, 25)
    base = int(datetime(2026, 10, 25, tzinfo=UTC).timestamp())
    a = "".join(
        encode_event(s, st)
        for s, st in [
            (3600, TEAM1),
            (7200, QUEUE),
            (7300, TEAM2),
            (9000, LEFT),
            (10000, TEAM1),
            (10600, LEFT),
        ]
    )
    # b 跨天延续（第 0 秒）不算进服，最后一段到 until 仍在服
    b = encode_event(0, TEAM2)
    until = base + 3600 * 5
    out = tally_playtime([(day, 1, a), (day, 2, b)], base, until)
    assert out[1]["seconds"] == 3600 + 1700 + 600
    assert out[1]["joins"] == 2
    assert out[1]["last_seen"] == base + 10600
    assert out[1]["online"] is False
    assert out[2] == {
        "seconds": until - base,
        "joins": 0,
        "days": {date(2026, 10, 25)},  # UTC 零点 = 北京 8 点，同一天
        "last_seen": until,
        "online": True,
    }
    # 窗口从 a 第一段中间开始：只算窗口内的部分，窗口前的进服不算
    clipped = tally_playtime([(day, 1, a)], base + 5400, until)
    assert clipped[1]["seconds"] == 1800 + 1700 + 600
    assert clipped[1]["joins"] == 1


async def test_leaderboard_ranks_by_team_time(
    test_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spc, "datetime", _Clock)
    monkeypatch.setattr(spc, "roster_tracker", RosterTracker())
    start = datetime.now(UTC) - timedelta(hours=1)
    a, b, c = 201, 202, 203
    await _round(test_session, start, {a: TEAM1, b: QUEUE, c: SPECTATOR})
    await _round(test_session, start + timedelta(minutes=1), {a: TEAM1, b: TEAM2, c: SPECTATOR})
    await _round(test_session, start + timedelta(minutes=2), {b: TEAM2})
    _Clock.current = start + timedelta(minutes=3)

    board = await spc.get_leaderboard(test_session, 1, days=1)
    # 观战的 c 没有在队时长，不上榜；b 排队那一分钟不算
    assert board.total_players == 2
    assert [(e.persona_id, e.seconds, e.online) for e in board.items] == [
        (a, 120, False),
        (b, 120, True),
    ]
    assert board.items[0].name == "p201"
    assert board.items[0].joins == 1 and board.items[0].days == 1


def test_tally_visits_joins_days_and_restarts() -> None:
    d1, d2 = date(2026, 10, 25), date(2026, 10, 26)
    base = int(datetime(2026, 10, 25, tzinfo=UTC).timestamp())
    nxt = base + 86400

    def ev(*items: tuple[int, int]) -> str:
        return "".join(encode_event(sec, st) for sec, st in items)

    rows = [
        (d1, 1, ev((3600, TEAM1), (7200, LEFT), (8000, QUEUE), (8100, LEFT), (80000, TEAM2))),
        # 跨天第 0 秒延续；600 秒服重启：旧实例离开、新实例同一秒进入，不算断开
        (d2, 1, ev((0, TEAM2), (600, LEFT))),
        (d2, 2, ev((600, TEAM1), (900, LEFT), (2000, SPECTATOR))),
    ]
    assert tally_visits(rows) == [
        {"start": base + 3600, "end": base + 7200, "seated": True},
        {"start": base + 8000, "end": base + 8100, "seated": False},
        {"start": base + 80000, "end": nxt + 900, "seated": True},
        {"start": nxt + 2000, "end": None, "seated": False},
    ]
    assert tally_visits([]) == []


async def test_find_visits_by_name_or_pid(test_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spc, "datetime", _Clock)
    monkeypatch.setattr(spc, "roster_tracker", RosterTracker())
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=1)
    t = [int((start + timedelta(minutes=i)).timestamp()) for i in range(5)]
    a, b, c = 101, 1010, 202
    await _round(test_session, start, {a: TEAM1, c: TEAM2})
    await _round(test_session, start + timedelta(minutes=1), {a: TEAM1, b: QUEUE, c: TEAM2})
    await _round(test_session, start + timedelta(minutes=2), {b: TEAM2, c: TEAM2})
    await _round(test_session, start + timedelta(minutes=3), {a: SPECTATOR, b: TEAM2, c: TEAM2})
    _Clock.current = start + timedelta(minutes=4)

    def view(res) -> list[tuple]:
        return [
            (p.persona_id, p.name, [(v.start, v.end, v.seated) for v in p.visits])
            for p in res.players
        ]

    # 名字片段不分大小写：完全对上的排前面，其次是开头对上的；时段从新到旧
    res = await spc.find_visits(test_session, 1, " P101 ")
    assert view(res) == [
        (a, "p101", [(t[3], None, False), (t[0], t[2], True)]),
        (b, "p1010", [(t[1], None, True)]),
    ]
    assert res.more is False
    # PID 完全对上排第一，名字里含这串数字的排后面
    found = await spc.find_visits(test_session, 1, "101")
    assert [p.persona_id for p in found.players] == [a, b]
    found = await spc.find_visits(test_session, 1, "1010")
    assert [p.persona_id for p in found.players] == [b]
    assert (await spc.find_visits(test_session, 1, "zzz")).players == []
    # LIKE 的通配符按字面匹配
    assert (await spc.find_visits(test_session, 1, "p_0")).players == []
    monkeypatch.setattr(spc, "VISIT_PLAYERS", 1)
    res = await spc.find_visits(test_session, 1, "p")
    assert len(res.players) == 1 and res.more is True


async def test_visits_route_validates_query(client) -> None:
    res = await client.get("/api/v1/bf1/servers/1/visits", params={"q": "a"})
    assert res.status_code == 422
    res = await client.get("/api/v1/bf1/servers/1/visits", params={"q": "nobody"})
    assert res.status_code == 200 and res.json() == {"players": [], "more": False}
