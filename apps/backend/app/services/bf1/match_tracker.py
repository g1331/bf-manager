"""BF1 对局跟踪：每分钟随全服快照跑一轮，用生涯差分算出每局每人的战绩

依据（2026-10-27 实测，见 round_stats）：生涯只在结算和中途退出时写入。所以

- 有人进服（含开始跟踪时已经在服的人），查一次核心生涯作为基线；
- 有人离开，下一次查询拿到的就是他离开时写进去的值，即他这一局的终值；
- 每轮从每台服挑几个基线稳定的人只查「完成局数」，有一半以上 +1 就说明这台服结算了；
  等下一轮（约一分钟，让整服写完）再把在服的人全查一遍，作为这一局的终值、下一局的基线；
- 进服后过一阵复查一次：刚从别的服过来的人，上一台服的结算可能几分钟后才写入，局数或胜负
  变了就换成新的基线，免得算进这一局。

状态都在内存里：服务重启或快照断档后从头开始，接手时已经开打的局标记为 observed_start=False。
查询经注入的 fetch 发出，本模块不碰数据库与网络，便于测试。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loguru import logger

from app.domain.games.bf1.round_stats import (
    FINISHED,
    LEFT_EARLY,
    LOSSES,
    PROBE_NAMES,
    ROUNDS,
    SUSPECT,
    WINS,
    diff,
    round_stat_names,
    to_vector,
)
from app.services.bf1.server_roster_service import TEAM1, TEAM2, Rosters

Fetch = Callable[[list[int], dict[str, list[str]]], Awaitable[dict[int, dict[str, float]]]]

# 进服后多久复查基线；实测别的服的结算最晚在进服 8 分钟后才写入
RECHECK_AFTER = 600
# 每台服每轮探测几个人，要过半 +1 才算结算，至少 2 人（只剩 1 个可探测的人时 1 人即可）
PROBE_SIZE = 4
# 基线至少要这么旧才拿来探测，刚查到的值还没机会变
PROBE_MIN_AGE = 50
# 两轮间隔超过它（重启、快照失败）就丢掉全部状态，与名单时间线的断档阈值一致
MAX_GAP = 420
# 每轮最多查这么多人的核心生涯（每 64 人、每个类别一个请求，即 30 个请求）。刚启动时几千人都要
# 查基线，分几轮查完；平时每分钟进出、结算加复查约七百人
MAX_QUERY_PER_TICK = 960


@dataclass
class Seat:
    """一个人在当前这一局里的状态"""

    since: int  # 进入这一局的时刻（进服，或上一局结算后延续过来）
    team: int = 0  # 最近一次在队的队伍 1 / 2；只排过队、观过战的为 0
    base: list[int] | None = None  # 基线向量，None 表示还没查到
    base_at: int = 0
    recheck_at: int | None = None
    left: bool = False
    end: list[int] | None = None  # 离开后查到的终值


@dataclass
class OpenRound:
    started_at: int
    observed_start: bool
    seats: dict[int, Seat] = field(default_factory=dict)
    maps: Counter[tuple[str | None, str | None]] = field(default_factory=Counter)
    settle_seen_at: int | None = None  # 探测到结算的时刻，下一轮收尾


@dataclass
class RoundLine:
    pid: int
    team: int
    status: int
    delta: list[int]


@dataclass
class ClosedRound:
    game_id: int
    started_at: int
    ended_at: int
    observed_start: bool
    settled: bool
    map_name: str | None
    game_mode: str | None
    winner: int | None
    lines: list[RoundLine]


def _team(state: int) -> int:
    return {TEAM1: 1, TEAM2: 2}.get(state, 0)


def _line(pid: int, seat: Seat, end: list[int]) -> RoundLine | None:
    if seat.base is None or seat.team == 0:
        return None
    delta = diff(end, seat.base)
    if delta is None or not any(delta):
        return None
    rounds = delta[ROUNDS]
    status = FINISHED if rounds == 1 else LEFT_EARLY if rounds == 0 else SUSPECT
    return RoundLine(pid, seat.team, status, delta)


def _winner(lines: list[RoundLine]) -> int | None:
    """按打完的人里各队的胜败多数判胜方：一队多数胜、另一队多数败才算数。"""
    score = {1: 0, 2: 0}
    for ln in lines:
        if ln.status == FINISHED:
            score[ln.team] += ln.delta[WINS] - ln.delta[LOSSES]
    if score[1] > 0 > score[2]:
        return 1
    if score[2] > 0 > score[1]:
        return 2
    return None


def _sync_seats(rnd: OpenRound, roster: dict[int, tuple[int, str]], now: int) -> None:
    for pid, (state, _) in roster.items():
        seat = rnd.seats.get(pid)
        if seat is None:
            seat = rnd.seats[pid] = Seat(since=now, recheck_at=now + RECHECK_AFTER)
        elif seat.left:
            # 离开后又回来：沿用原基线，两段的增量合在这一局里；离开时查到的终值作废
            seat.left, seat.end = False, None
        # 探测到结算后不再跟队：换图时常重新分队，收尾那一轮的名单已是下一局的队伍
        if (team := _team(state)) and rnd.settle_seen_at is None:
            seat.team = team
    for pid, seat in list(rnd.seats.items()):
        if pid not in roster and not seat.left:
            seat.left = True
        if seat.left and seat.base is None:
            del rnd.seats[pid]  # 没查到基线就走了，算不出增量


class MatchTracker:
    def __init__(self) -> None:
        self.rounds: dict[int, OpenRound] = {}
        self.last_tick: int | None = None

    async def tick(
        self,
        rosters: Rosters,
        maps: dict[int, tuple[str | None, str | None]],
        now: int,
        fetch: Fetch,
    ) -> list[ClosedRound]:
        """处理一轮快照名单，返回这一轮收尾的对局。查询失败时保留状态，下一轮重试。"""
        if self.last_tick is not None and now - self.last_tick > MAX_GAP:
            logger.info("BF1 match tracker gap {}s, dropping open rounds", now - self.last_tick)
            self.rounds = {}
        self.last_tick = now
        closed: list[ClosedRound] = []

        self._sync(rosters, maps, now)
        await self._probe(now, fetch)

        settling = {
            gid
            for gid, rnd in self.rounds.items()
            if rnd.settle_seen_at is not None and rnd.settle_seen_at < now
        }
        vectors: dict[int, list[int]] = {}
        if wanted := self._wanted(now, settling):
            try:
                values = await fetch(sorted(wanted), round_stat_names())
            except Exception as e:
                logger.warning("BF1 match tracker stats query failed, retry next round: {}", e)
                return closed
            vectors = {pid: to_vector(v) for pid, v in values.items()}
            self._apply(vectors, now)

        for gid in list(self.rounds):
            rnd = self.rounds[gid]
            if gid in settling:
                closed.append(self._close(gid, rnd, vectors, now, settled=True))
            elif gid not in rosters and all(s.left for s in rnd.seats.values()):
                # 服务器从快照里消失（关服、清空），没等到结算
                closed.append(self._close(gid, rnd, vectors, now, settled=False))
                del self.rounds[gid]
        return [c for c in closed if c.lines]

    def _sync(
        self,
        rosters: Rosters,
        maps: dict[int, tuple[str | None, str | None]],
        now: int,
    ) -> None:
        """按本轮名单登记进出与换队；从快照里消失的服，在服的人全部记为离开。"""
        for gid, roster in rosters.items():
            rnd = self.rounds.get(gid)
            if rnd is None:
                # 第一次见到的服（含刚启动时的全部服）：局早已开打，开局时间未知
                rnd = self.rounds[gid] = OpenRound(started_at=now, observed_start=False)
            if rnd.settle_seen_at is None:
                rnd.maps[maps.get(gid, (None, None))] += 1
            _sync_seats(rnd, roster, now)
        for gid, rnd in self.rounds.items():
            if gid not in rosters:
                _sync_seats(rnd, {}, now)

    async def _probe(self, now: int, fetch: Fetch) -> None:
        """每台服挑基线最旧的几个在服玩家，只查完成局数，过半 +1 就记下结算时刻。

        刚进服的人可能带着别的服迟到的结算，但那是零星个别人，过半且至少 2 人的门槛挡得住；
        不要求已复查，否则刚启动的 10 分钟里谁都不能探测，这期间的结算会漏掉。
        """
        picks: dict[int, list[int]] = {}
        for gid, rnd in self.rounds.items():
            if rnd.settle_seen_at is not None:
                continue
            stable = sorted(
                (s.base_at, pid)
                for pid, s in rnd.seats.items()
                if not s.left and s.base is not None and now - s.base_at >= PROBE_MIN_AGE
            )
            if stable:
                picks[gid] = [pid for _, pid in stable[:PROBE_SIZE]]
        pids = sorted({p for ps in picks.values() for p in ps})
        if not pids:
            return
        try:
            values = await fetch(pids, PROBE_NAMES)
        except Exception as e:
            logger.warning("BF1 match tracker probe failed: {}", e)
            return
        name = PROBE_NAMES[next(iter(PROBE_NAMES))][0]
        for gid, ps in picks.items():
            rnd = self.rounds[gid]
            hits = 0
            for pid in ps:
                base = rnd.seats[pid].base
                if pid in values and base is not None and round(values[pid][name]) > base[ROUNDS]:
                    hits += 1
            if hits * 2 > len(ps) and (hits >= 2 or len(ps) == 1):
                rnd.settle_seen_at = now

    def _wanted(self, now: int, settling: set[int]) -> set[int]:
        """本轮要查的人，超过上限时按优先级截断，其余留到下一轮。

        结算收尾最急（晚了新一局的退出会混进来），其次是刚离开的人（晚了可能混进别的服），
        再是复查，新进服的基线最不急：局中生涯不变，晚一两分钟查也一样。
        """
        ranked: list[tuple[int, int]] = []
        for gid, rnd in self.rounds.items():
            for pid, s in rnd.seats.items():
                if not s.left and gid in settling:
                    ranked.append((0, pid))  # 结算收尾
                elif s.base is None:
                    ranked.append((3, pid))  # 新进服
                elif s.left and s.end is None:
                    ranked.append((1, pid))  # 刚离开
                elif not s.left and self._recheck_due(rnd, s, now):
                    ranked.append((2, pid))  # 到点复查
        out: set[int] = set()
        for _, pid in sorted(ranked):
            if len(out) >= MAX_QUERY_PER_TICK:
                break
            out.add(pid)
        return out

    @staticmethod
    def _recheck_due(rnd: OpenRound, s: Seat, now: int) -> bool:
        # 已探测到结算的服不复查：此时局数变了是这一局自己的结算，换基线就把这局丢了
        return rnd.settle_seen_at is None and s.recheck_at is not None and s.recheck_at <= now

    def _apply(self, vectors: dict[int, list[int]], now: int) -> None:
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                vec = vectors.get(pid)
                if vec is None:
                    continue
                if s.base is None:
                    s.base, s.base_at = vec, now
                elif s.left and s.end is None:
                    s.end = vec
                elif self._recheck_due(rnd, s, now):
                    if any(vec[i] != s.base[i] for i in (ROUNDS, WINS, LOSSES)):
                        s.base, s.base_at = vec, now
                    s.recheck_at = None

    def _close(
        self,
        gid: int,
        rnd: OpenRound,
        vectors: dict[int, list[int]],
        now: int,
        *,
        settled: bool,
    ) -> ClosedRound:
        """收尾一局：离开的人用离开时的终值，在服的人用本轮查到的值。在服的人带着本轮的值进下一局。"""
        lines: list[RoundLine] = []
        carry: dict[int, Seat] = {}
        boundary = rnd.settle_seen_at or now
        for pid, s in rnd.seats.items():
            if s.since > boundary:
                # 探测到结算之后才进来的，属于下一局；进来又走了的只打了一小段，不记
                if not s.left:
                    carry[pid] = s
                continue
            end = s.end if s.left else vectors.get(pid)
            if end is not None and (ln := _line(pid, s, end)) is not None:
                lines.append(ln)
            if not s.left:
                carry[pid] = (
                    Seat(since=boundary, team=s.team, base=end, base_at=now)
                    if end is not None
                    else Seat(since=boundary, team=s.team, recheck_at=now + RECHECK_AFTER)
                )
        (map_name, game_mode), _ = (rnd.maps.most_common(1) or [((None, None), 0)])[0]
        winner = _winner(lines)
        if winner is not None:
            # 局中换过队的人以结算的胜负为准
            for ln in lines:
                if ln.status == FINISHED and ln.delta[WINS] != ln.delta[LOSSES]:
                    ln.team = winner if ln.delta[WINS] else 3 - winner
        if settled:
            self.rounds[gid] = OpenRound(started_at=boundary, observed_start=True, seats=carry)
        return ClosedRound(
            game_id=gid,
            started_at=rnd.started_at,
            ended_at=boundary,
            observed_start=rnd.observed_start,
            settled=settled and any(ln.status == FINISHED for ln in lines),
            map_name=map_name,
            game_mode=game_mode,
            winner=winner,
            lines=lines,
        )


tracker = MatchTracker()
