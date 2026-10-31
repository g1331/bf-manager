"""实时名单解析：载入中状态、带等级的排队者、未连上时的进服时间。"""

from __future__ import annotations

from app.domain.ea.data_handle import BlazeData

ZHCN = int.from_bytes(b"zhCN", "big")


def _player(pid: int, *, stat: int, tidx: int, role: str = "soldier", **extra) -> dict:
    return {
        "PID": pid,
        "NAME": f"p{pid}",
        "EXID": pid,
        "ROLE": role,
        "TIDX": tidx,
        "STAT": stat,
        "JGTS": 1_793_440_000_000_000,
        "LOC": ZHCN,
        "PATT": {"rank": "50", "latency": "40"},
        **extra,
    }


def _parse(roster: list[dict]) -> dict:
    data = {"GID": 7, "GNAM": "s", "ATTR": {}, "CAP": [64, 0, 4, 0], "ROST": roster}
    return BlazeData.player_list_handle({"type": "Result", "data": {"GDAT": [data]}})[7]


def test_loading_flag_follows_stat() -> None:
    room = _parse(
        [
            _player(1, stat=4, tidx=0),
            _player(2, stat=2, tidx=1, JGTS=0, PATT={"rank": "60", "latency": "-1"}),
            _player(3, stat=0, tidx=1, JGTS=0, PATT={}),
            _player(4, stat=2, tidx=65535, role=""),
        ]
    )
    by_pid = {p["pid"]: p for p in room["players"] + room["spectators"]}
    assert {pid: p["loading"] for pid, p in by_pid.items()} == {1: False, 2: True, 3: True, 4: True}
    # 还没连上的人 JGTS 为 0，不能解析成 1970 年
    assert by_pid[2]["join_time"] is None
    assert by_pid[1]["join_time"] == 1_793_440_000


def test_queued_player_with_rank_stays_in_queue() -> None:
    # STAT 1 的排队者已带等级，以前按「等级为 0」判断会被当成队伍玩家，再因队位无效被丢掉
    room = _parse(
        [
            _player(1, stat=1, tidx=65535, PATT={"rank": "23", "latency": "-1"}),
            _player(2, stat=0, tidx=65535, PATT={}),
            _player(3, stat=4, tidx=65535, role=""),
        ]
    )
    assert [p["pid"] for p in room["queues"]] == [1, 2]
    assert [p["pid"] for p in room["spectators"]] == [3]
    assert room["players"] == []
    assert not any(p["loading"] for p in room["queues"])
