"""服务器快照：名单事件编解码、快照名单提取，以及多轮差分写入后的读取。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.api.errors import NotFoundError
from app.models.bf1.server_roster import Bf1ServerPlayerDay
from app.schemas.bf1.server import ServerSummary
from app.services.bf1 import server_player_count_service as spc
from app.services.bf1.server_roster_service import (
    QUEUE,
    SPECTATOR,
    TEAM1,
    TEAM2,
    RosterTracker,
    decode_events,
    encode_event,
    extract_rosters,
)
from sqlalchemy import func, select


def test_event_codec_roundtrip() -> None:
    events = [(0, TEAM1), (86399, TEAM2), (43210, QUEUE), (1, 0), (7, SPECTATOR)]
    packed = "".join(encode_event(sec, state) for sec, state in events)
    assert len(packed) == 4 * len(events)
    assert decode_events(packed) == events


def _p(pid: int, tidx: int, *, role: str = "soldier") -> dict:
    return {"PID": pid, "NAME": f"p{pid}", "TIDX": tidx, "ROLE": role, "HNET": "secret"}


def test_extract_rosters_private_only_without_private_fields() -> None:
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
        b: ("team1", "switched"),
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
