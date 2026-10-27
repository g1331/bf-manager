"""BF1 服务器名单时间线（服务器快照）

全服统计每分钟拿到的快照里带着每个服的完整名单（ROST）。这里和上一轮名单做差分，只把变化
写进库：每人每服每天一行，进服、换队、离开各是一个事件，追加在这一行的 events 后面。
换队或几分钟内离开又回来都不新增行，名字另存一张表。

事件是 (当天第几秒, 状态) 打包成的 3 字节整数，再写成 4 个 base64 字符：Postgres 与测试用的
sqlite 都能直接用 || 追加文本，存储和裸 4 字节一样。某一时刻的名单 = 每人在该时刻之前的
最后一个事件。所有事件的时间都是采样轮次的时间，与人数点 sampled_at 对齐，查询时按秒相等
匹配「这一轮的进出」。

上一轮的名单留在进程内存里，重启后从当天的行解码重建；两轮间隔太久（重启、快照失败）就把
还在线的人统一记为离开，免得断档期间被算成一直在线。
"""

from __future__ import annotations

import base64
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bf1.server_player_count import Bf1ServerPlayerCount
from app.models.bf1.server_roster import Bf1PlayerName, Bf1ServerPlayerDay

LEFT, TEAM1, TEAM2, QUEUE, SPECTATOR = range(5)
SLOT_NAMES = {TEAM1: "team1", TEAM2: "team2", QUEUE: "queue", SPECTATOR: "spectator"}
QUEUE_TIDX = 65535

RETENTION = timedelta(days=7)
# 排行榜按北京时间数活跃天数，玩家感知的「一天」从零点开始，而不是 UTC 零点（北京 8 点）
BEIJING = timezone(timedelta(hours=8))
# 两轮名单间隔超过它就视为断档，与人数曲线的 MAX_SAMPLE_SPAN 一致
MAX_GAP_SECONDS = 420
# 一条 upsert 的行数上限，避开 Postgres 单语句 32767 个参数的限制
WRITE_CHUNK = 2000

Rosters = dict[int, dict[int, tuple[int, str]]]  # game_id → pid → (状态, 名字)


def encode_event(sec: int, state: int) -> str:
    return base64.b64encode(((sec << 3) | state).to_bytes(3, "big")).decode()


def decode_events(events: str) -> list[tuple[int, int]]:
    out = []
    for i in range(0, len(events), 4):
        v = int.from_bytes(base64.b64decode(events[i : i + 4]), "big")
        out.append((v >> 3, v & 7))
    return out


def _day_and_sec(ts: int) -> tuple[date, int]:
    dt = datetime.fromtimestamp(ts, UTC)
    # 第 0 秒留给跨天时延续在线状态的事件，本轮变化至少记在第 1 秒
    return dt.date(), max(dt.hour * 3600 + dt.minute * 60 + dt.second, 1)


def _slot(player: dict[str, Any]) -> int:
    # 生产实测：观战者 ROLE 为空、TIDX 65535、STYP 2；排队者 ROLE 为 soldier、TIDX 65535、STYP 0
    if player.get("ROLE") == "":
        return SPECTATOR
    tidx = player.get("TIDX")
    if tidx in (0, 1):
        return TEAM1 + int(tidx)
    return QUEUE


def extract_rosters(updates: Iterable[dict[str, Any]]) -> Rosters:
    """从快照 UPDT 项取出各服名单（官服也记）。只留 PID、名字与所在位置，HNET 等隐私字段不往外传。"""
    rosters: Rosters = {}
    for update in updates:
        game = update.get("GAM") or update
        gid = game.get("GID")
        if gid is None:
            continue
        rosters[int(gid)] = {
            int(p["PID"]): (_slot(p), str(p.get("NAME") or ""))
            for p in game.get("ROST") or []
            if p.get("PID")
        }
    return rosters


def _aware(dt: datetime) -> datetime:
    # sqlite 读回的是无时区时间，按写入时的 UTC 补上
    return dt.replace(tzinfo=dt.tzinfo or UTC)


class RosterTracker:
    """记住上一轮名单，把本轮变化写成事件。

    stage 只往会话里加语句、不提交；调用方提交成功后 commit，失败则 reset，下一轮从库里重建，
    保证内存与库一致。
    """

    def __init__(self) -> None:
        self._open: dict[int, dict[int, int]] | None = None
        self._last_ts: int | None = None
        self._pending: tuple[dict[int, dict[int, int]], int] | None = None

    def reset(self) -> None:
        self._open = self._last_ts = self._pending = None

    def commit(self) -> None:
        if self._pending is not None:
            self._open, self._last_ts = self._pending
            self._pending = None

    async def _load(self, db: AsyncSession) -> None:
        """冷启动：上一轮名单 = 上一个有名单的采样日里、最后一个事件仍在线的人。"""
        self._open, self._last_ts = {}, None
        last = await db.scalar(
            select(func.max(Bf1ServerPlayerCount.sampled_at)).where(
                Bf1ServerPlayerCount.joined_count.is_not(None)
            )
        )
        if last is None:
            return
        self._last_ts = int(_aware(last).timestamp())
        day, _ = _day_and_sec(self._last_ts)
        rows = await db.execute(
            select(
                Bf1ServerPlayerDay.game_id, Bf1ServerPlayerDay.pid, Bf1ServerPlayerDay.events
            ).where(Bf1ServerPlayerDay.day == day)
        )
        for gid, pid, events in rows:
            state = decode_events(events[-4:])[0][1]
            if state != LEFT:
                self._open.setdefault(gid, {})[pid] = state

    async def stage(
        self, db: AsyncSession, rosters: Rosters, now: datetime
    ) -> dict[int, tuple[int, int]]:
        """把本轮名单相对上一轮的变化加进会话，返回各服 (进入, 退出) 人数。"""
        cold = self._open is None
        if cold:
            await self._load(db)
        prev, last_ts = self._open or {}, self._last_ts
        ts = int(now.timestamp())
        day, sec = _day_and_sec(ts)
        appends: dict[tuple[int, date, int], str] = defaultdict(str)
        names: dict[int, str] = {}
        prev, new_day = _carry_over(prev, last_ts, ts, appends)

        counts: dict[int, tuple[int, int]] = {}
        for gid in prev.keys() | rosters.keys():
            old, new = prev.get(gid, {}), rosters.get(gid, {})
            joined = 0
            for pid, (state, name) in new.items():
                before = old.get(pid, LEFT)
                if state != before:
                    appends[(gid, day, pid)] += encode_event(sec, state)
                if before == LEFT:
                    joined += 1
                if before == LEFT or new_day:
                    names[pid] = name
            gone = old.keys() - new.keys()
            for pid in gone:
                appends[(gid, day, pid)] += encode_event(sec, LEFT)
            counts[gid] = (joined, len(gone))

        await _write_events(db, appends)
        await _write_names(db, names, now)
        if cold or new_day:
            cutoff = now - RETENTION
            await db.execute(
                delete(Bf1ServerPlayerDay).where(Bf1ServerPlayerDay.day < cutoff.date())
            )
            await db.execute(delete(Bf1PlayerName).where(Bf1PlayerName.seen_at < cutoff))
        self._pending = (
            {
                gid: {pid: state for pid, (state, _) in ps.items()}
                for gid, ps in rosters.items()
                if ps
            },
            ts,
        )
        return counts


tracker = RosterTracker()


def _carry_over(
    prev: dict[int, dict[int, int]],
    last_ts: int | None,
    ts: int,
    appends: dict[tuple[int, date, int], str],
) -> tuple[dict[int, dict[int, int]], bool]:
    """处理断档与跨天，返回 (用于差分的上一轮名单, 是否跨天)。"""
    if last_ts is None:
        return prev, False
    if ts - last_ts > MAX_GAP_SECONDS:
        # 断档：只知道这些人在上一轮之后某时离开，记在上一轮后一分钟，不算进任何一轮的退出
        last_day, last_sec = _day_and_sec(last_ts)
        leave = encode_event(min(last_sec + 60, 86399), LEFT)
        for gid, players in prev.items():
            for pid in players:
                appends[(gid, last_day, pid)] += leave
        return {}, False
    day = _day_and_sec(ts)[0]
    if not prev or _day_and_sec(last_ts)[0] == day:
        return prev, False
    # 跨天：给仍在线的人在新的一天开一行，第 0 秒延续上一轮的状态
    for gid, players in prev.items():
        for pid, state in players.items():
            appends[(gid, day, pid)] += encode_event(0, state)
    return prev, True


def insert_for(db: AsyncSession, table: Any) -> Any:
    """按方言取支持 on_conflict 的 insert：生产是 Postgres，测试是 sqlite"""
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    return insert(table)


def _chunks(items: list[Any]) -> Iterable[list[Any]]:
    for i in range(0, len(items), WRITE_CHUNK):
        yield items[i : i + WRITE_CHUNK]


async def _write_events(db: AsyncSession, appends: dict[tuple[int, date, int], str]) -> None:
    rows = [{"game_id": g, "day": d, "pid": p, "events": e} for (g, d, p), e in appends.items()]
    for chunk in _chunks(rows):
        stmt = insert_for(db, Bf1ServerPlayerDay).values(chunk)
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["game_id", "day", "pid"],
                set_={"events": Bf1ServerPlayerDay.events + stmt.excluded.events},
            )
        )


async def _write_names(db: AsyncSession, names: dict[int, str], now: datetime) -> None:
    rows = [{"pid": p, "name": n[:64], "seen_at": now} for p, n in names.items()]
    for chunk in _chunks(rows):
        stmt = insert_for(db, Bf1PlayerName).values(chunk)
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["pid"],
                set_={"name": stmt.excluded.name, "seen_at": stmt.excluded.seen_at},
            )
        )


async def read_roster(db: AsyncSession, game_id: int, ts: int) -> list[dict[str, Any]]:
    """game_id 这一局在采样时刻 ts 的名单，附这一轮的变化。

    返回在场的人（change 为 joined / seated / switched / None）和这一轮离开的人（change 为 left，
    slot 是离开前的位置），按 pid 排序。
    """
    day, sec = _day_and_sec(ts)
    rows = (
        await db.execute(
            select(Bf1ServerPlayerDay.pid, Bf1ServerPlayerDay.events).where(
                Bf1ServerPlayerDay.game_id == game_id, Bf1ServerPlayerDay.day == day
            )
        )
    ).all()
    out: list[dict[str, Any]] = []
    for pid, events in rows:
        before = after = LEFT
        for at, state in decode_events(events):
            if at < sec:
                before = state
            if at <= sec:
                after = state
        if after != LEFT:
            if before == LEFT:
                change = "joined"
            elif before in (QUEUE, SPECTATOR) and after in (TEAM1, TEAM2):
                change = "seated"  # 排队或观战的人进场，不是换队
            else:
                change = "switched" if before != after else None
            out.append({"pid": pid, "slot": SLOT_NAMES[after], "change": change})
        elif before != LEFT:
            out.append({"pid": pid, "slot": SLOT_NAMES[before], "change": "left"})
    if out:
        names = await read_names(db, [p["pid"] for p in out])
        for p in out:
            p["name"] = names.get(p["pid"])
    return sorted(out, key=lambda p: p["pid"])


def tally_playtime(
    rows: Iterable[tuple[date, int, str]], since: int, until: int
) -> dict[int, dict[str, Any]]:
    """按 (UTC 日期, pid, 事件串) 累计每人在 [since, until) 内的在队时长。

    只有 team1 / team2 计时，排队与观战不算；活跃天数按北京时间日期去重；进服次数只数从离开变为
    在服的事件，第 0 秒的跨天延续不算。最后一段到当天结束（今天则到 until）仍在服的记为 online。
    """
    out: dict[int, dict[str, Any]] = {}
    for day, pid, events in rows:
        base = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
        day_end = min(base + 86400, until)
        evs = decode_events(events)
        t = out.setdefault(
            pid, {"seconds": 0, "joins": 0, "days": set(), "last_seen": 0, "online": False}
        )
        prev = LEFT
        for i, (at, state) in enumerate(evs):
            start = base + at
            end = base + evs[i + 1][0] if i + 1 < len(evs) else day_end
            lo, hi = max(start, since), min(end, until)
            if state != LEFT and prev == LEFT and at > 0 and since <= start < until:
                t["joins"] += 1
            if state != LEFT and hi > lo:
                t["last_seen"] = max(t["last_seen"], hi)
                if state in (TEAM1, TEAM2):
                    t["seconds"] += hi - lo
                    t["days"].add(datetime.fromtimestamp(lo, BEIJING).date())
                if i + 1 == len(evs) and end >= until:
                    t["online"] = True
            prev = state
    return out


async def read_playtime(
    db: AsyncSession, game_ids: Iterable[int], since: int, until: int
) -> dict[int, dict[str, Any]]:
    """这些局（同一台服重启前后的 game_id）在 [since, until) 内每人的在队时长等。"""
    since_day = datetime.fromtimestamp(since, UTC).date()
    rows = await db.execute(
        select(Bf1ServerPlayerDay.day, Bf1ServerPlayerDay.pid, Bf1ServerPlayerDay.events).where(
            Bf1ServerPlayerDay.game_id.in_(list(game_ids)), Bf1ServerPlayerDay.day >= since_day
        )
    )
    return tally_playtime(rows.tuples().all(), since, until)


async def read_names(db: AsyncSession, pids: list[int]) -> dict[int, str]:
    rows = await db.execute(
        select(Bf1PlayerName.pid, Bf1PlayerName.name).where(Bf1PlayerName.pid.in_(pids))
    )
    return dict(rows.tuples().all())
