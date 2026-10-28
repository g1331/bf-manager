"""BF1 对局跟踪：每分钟随全服快照跑一轮，用生涯差分算出每局每人的战绩

依据（2026-10-27 实测，见 round_stats）：生涯只在结算和中途退出时写入。所以

- 有人进服（含开始跟踪时已经在服的人），查一次核心生涯作为基线；
- 有人离开，下一次查询拿到的就是他离开时写进去的值，即他这一局的终值；
- 每轮从每台服挑几个基线稳定的人只查「完成局数」，有一半以上 +1 就说明这台服结算了；
  等下一轮（约一分钟，让整服写完）再把在服的人全查一遍，作为这一局的终值、下一局的基线；
- 进服后过一阵复查一次局数和胜负：之前打过的局的结算可能在进服后几分钟才写入（实测从离线
  直接进服的人也有 3–4%），变了就重查全量换成新的基线，免得算进这一局；
- 刚从别的服过来、离开那台服之后已经查到过值的人，直接拿这个值当基线，不再重查。

状态在内存里，停机时导出、启动时导入（见 round_service），重启间隔不超过 MAX_GAP 就接着跟；
快照断档太久则从头开始，接手时已经开打的局标记为 observed_start=False。
查询经注入的 fetch 发出，本模块不碰数据库与网络，便于测试。各环节查了多少人记在 ea_metrics 的
跟踪器事件里，用来判断哪些查询可以省。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger

from app.core import ea_metrics
from app.domain.games.bf1.round_stats import (
    FINISHED,
    LEFT_EARLY,
    LOSSES,
    PROBE_NAMES,
    RECHECK_FIELDS,
    RECHECK_NAMES,
    ROUND_STATS,
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
# 每台服每轮先探测 2 人，结论不一致时同一轮补到 4 人；要过半 +1 才算结算，至少 2 人
# （只剩 1 个可探测的人时 1 人即可）
PROBE_FIRST = 2
PROBE_SIZE = 4
# 基线至少要这么旧才拿来探测，刚查到的值还没机会变
PROBE_MIN_AGE = 50
# 两轮间隔超过它（重启、快照失败）就丢掉全部状态，与名单时间线的断档阈值一致
MAX_GAP = 420
# 每轮最多查这么多人的核心生涯（每 64 人、每个类别一个请求，即 30 个请求）。刚启动时几千人都要
# 查基线，分几轮查完；平时每分钟进出、结算加复查约七百人
MAX_QUERY_PER_TICK = 960
# 进服前这么久之内在别的服出现过，算换服过来的（可能带着上一台服迟到的结算）
HOP_WINDOW = 900
# 查到的向量留这么久，统计进服时有没有现成的值可当基线
VECTOR_KEEP = 600

# 本轮要查的人按原因计数时用的名字，下标即 _wanted 里的优先级
_WANT_REASONS = ("want_settle", "want_leave", "want_recheck", "want_join")


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
    hop: bool = False  # 进服前 HOP_WINDOW 内在别的服出现过
    rebase: bool = False  # 复查发现局数或胜负变了，要重查全量换基线


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


class MatchTracker:
    def __init__(self) -> None:
        self.rounds: dict[int, OpenRound] = {}
        self.last_tick: int | None = None
        # 每个人最近一次出现在哪台服、什么时候（只留 HOP_WINDOW 内的），判断进服是不是换服
        self.seen: dict[int, tuple[int, int]] = {}
        # 每个人最近查到的向量和时刻（只留 VECTOR_KEEP 内的）
        self.recent: dict[int, tuple[list[int], int]] = {}

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
            self.rounds, self.seen, self.recent = {}, {}, {}
        self.last_tick = now
        closed: list[ClosedRound] = []

        self._sync(rosters, maps, now)
        await self._probe(now, fetch)
        await self._recheck(now, fetch)

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
        prev = self.seen
        for gid, roster in rosters.items():
            rnd = self.rounds.get(gid)
            if rnd is None:
                # 第一次见到的服（含刚启动时的全部服）：局早已开打，开局时间未知
                rnd = self.rounds[gid] = OpenRound(started_at=now, observed_start=False)
            if rnd.settle_seen_at is None:
                rnd.maps[maps.get(gid, (None, None))] += 1
            self._sync_seats(gid, rnd, roster, prev, now)
        for gid, rnd in self.rounds.items():
            if gid not in rosters:
                self._sync_seats(gid, rnd, {}, prev, now)
        self.seen = {pid: v for pid, v in prev.items() if now - v[1] <= HOP_WINDOW}
        self.seen.update((pid, (gid, now)) for gid, roster in rosters.items() for pid in roster)
        self.recent = {pid: v for pid, v in self.recent.items() if now - v[1] <= VECTOR_KEEP}

    def _sync_seats(
        self,
        gid: int,
        rnd: OpenRound,
        roster: dict[int, tuple[int, str]],
        prev: dict[int, tuple[int, int]],
        now: int,
    ) -> None:
        for pid, (state, _) in roster.items():
            seat = rnd.seats.get(pid)
            if seat is None:
                last = prev.get(pid)
                hop = last is not None and last[0] != gid
                seat = rnd.seats[pid] = Seat(since=now, recheck_at=now + RECHECK_AFTER, hop=hop)
                ea_metrics.count_event("join_hop" if hop else "join_fresh")
                # 上次出现在服里之后才查到的值：那时人已经离开（离开时的写入已含在内），之后不在
                # 任何服里，生涯不会变，可以直接当基线；迟到的结算照常由复查兜住
                recent = self.recent.get(pid)
                if last is not None and recent is not None and recent[1] > last[1]:
                    seat.base, seat.base_at = list(recent[0]), recent[1]
                    ea_metrics.count_event("join_reused")
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

    async def _probe(self, now: int, fetch: Fetch) -> None:
        """每台服挑基线最旧的几个在服玩家，只查完成局数，过半 +1 就记下结算时刻。

        分两段：先查 2 人，两人都 +1 就算结算、都没变就算没结算；只有一人 +1 时同一轮再补查
        2 人，按 4 人过半判断。正常结算全服局数一起 +1，绝大多数服第一段就有结论。
        刚进服的人可能带着别的服迟到的结算，但那是零星个别人，过半且至少 2 人的门槛挡得住；
        不要求已复查，否则刚启动的 10 分钟里谁都不能探测，这期间的结算会漏掉。
        """
        candidates: dict[int, list[int]] = {}
        for gid, rnd in self.rounds.items():
            if rnd.settle_seen_at is not None:
                continue
            stable = sorted(
                (s.base_at, pid)
                for pid, s in rnd.seats.items()
                if not s.left and s.base is not None and now - s.base_at >= PROBE_MIN_AGE
            )
            if stable:
                candidates[gid] = [pid for _, pid in stable[:PROBE_SIZE]]
        if not candidates:
            return
        picks = {gid: ps[:PROBE_FIRST] for gid, ps in candidates.items()}
        hits = await self._probe_hits(picks, fetch)
        if hits is None:
            return
        more = {
            gid: ps[PROBE_FIRST:]
            for gid, ps in candidates.items()
            if len(ps) > PROBE_FIRST and 0 < hits[gid] < PROBE_FIRST
        }
        if more and (extra := await self._probe_hits(more, fetch)) is not None:
            for gid, ps in more.items():
                picks[gid] = picks[gid] + ps
                hits[gid] += extra[gid]
        for gid, ps in picks.items():
            h = hits[gid]
            if h * 2 > len(ps) and (h >= 2 or len(ps) == 1):
                self.rounds[gid].settle_seen_at = now

    async def _probe_hits(self, picks: dict[int, list[int]], fetch: Fetch) -> dict[int, int] | None:
        """查这些人的完成局数，返回每台服有几人比基线多；查询失败返回 None。"""
        pids = sorted({p for ps in picks.values() for p in ps})
        try:
            with ea_metrics.ea_source("tracker_probe"):
                values = await fetch(pids, PROBE_NAMES)
        except Exception as e:
            logger.warning("BF1 match tracker probe failed: {}", e)
            return None
        name = PROBE_NAMES[next(iter(PROBE_NAMES))][0]
        out: dict[int, int] = {}
        for gid, ps in picks.items():
            rnd = self.rounds[gid]
            out[gid] = sum(
                1
                for pid in ps
                if pid in values
                and (base := rnd.seats[pid].base) is not None
                and round(values[pid][name]) > base[ROUNDS]
            )
        return out

    async def _recheck(self, now: int, fetch: Fetch) -> None:
        """到点复查：只查局数和胜负，变了的标记 rebase，本轮的全量查询里重查基线。"""
        due = sorted(
            {
                pid
                for rnd in self.rounds.values()
                for pid, s in rnd.seats.items()
                if not s.left and s.base is not None and self._recheck_due(rnd, s, now)
            }
        )[:MAX_QUERY_PER_TICK]
        if not due:
            return
        try:
            values = await fetch(due, RECHECK_NAMES)
        except Exception as e:
            logger.warning("BF1 match tracker recheck failed, retry next round: {}", e)
            return
        ea_metrics.count_event("recheck_light", len(due))
        wanted = set(due)
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                if (
                    pid not in wanted
                    or s.left
                    or s.base is None
                    or not self._recheck_due(rnd, s, now)
                ):
                    continue
                v = values.get(pid)
                changed = v is not None and any(
                    round(v[ROUND_STATS[i][1]]) != s.base[i] for i in RECHECK_FIELDS
                )
                s.recheck_at, s.rebase = None, changed
                ea_metrics.count_event(
                    f"recheck_{'changed' if changed else 'same'}_{'hop' if s.hop else 'fresh'}"
                )

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
                elif not s.left and s.rebase and rnd.settle_seen_at is None:
                    ranked.append((2, pid))  # 复查发现变了，重查基线
        out: set[int] = set()
        for reason, pid in sorted(ranked):
            if len(out) >= MAX_QUERY_PER_TICK:
                break
            if pid not in out:
                out.add(pid)
                ea_metrics.count_event(_WANT_REASONS[reason])
        return out

    @staticmethod
    def _recheck_due(rnd: OpenRound, s: Seat, now: int) -> bool:
        # 已探测到结算的服不复查：此时局数变了是这一局自己的结算，换基线就把这局丢了
        return rnd.settle_seen_at is None and s.recheck_at is not None and s.recheck_at <= now

    def _apply(self, vectors: dict[int, list[int]], now: int) -> None:
        self.recent.update((pid, (vec, now)) for pid, vec in vectors.items())
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                vec = vectors.get(pid)
                if vec is None:
                    continue
                if s.base is None:
                    s.base, s.base_at = vec, now
                elif s.left and s.end is None:
                    s.end = vec
                elif s.rebase and rnd.settle_seen_at is None:
                    s.base, s.base_at, s.rebase = vec, now, False

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

    def dump(self) -> dict[str, Any]:
        """导出全部状态（JSON 可序列化），停机时存起来，重启后用 load 接着跟。"""
        return {
            "last_tick": self.last_tick,
            "rounds": {
                str(gid): {
                    "started_at": r.started_at,
                    "observed_start": r.observed_start,
                    "settle_seen_at": r.settle_seen_at,
                    "maps": [[m, mode, n] for (m, mode), n in r.maps.items()],
                    "seats": {str(pid): asdict(seat) for pid, seat in r.seats.items()},
                }
                for gid, r in self.rounds.items()
            },
            "seen": {str(pid): list(v) for pid, v in self.seen.items()},
            "recent": {str(pid): [vec, at] for pid, (vec, at) in self.recent.items()},
        }

    def load(self, data: dict[str, Any]) -> None:
        """导入 dump 的结果；先全部解析完再替换，数据不对就抛错、原状态不动。"""
        rounds = {
            int(gid): OpenRound(
                started_at=r["started_at"],
                observed_start=r["observed_start"],
                settle_seen_at=r["settle_seen_at"],
                maps=Counter({(m, mode): n for m, mode, n in r["maps"]}),
                seats={int(pid): Seat(**seat) for pid, seat in r["seats"].items()},
            )
            for gid, r in data["rounds"].items()
        }
        seen = {int(pid): (v[0], v[1]) for pid, v in data["seen"].items()}
        recent = {int(pid): (v[0], v[1]) for pid, v in data["recent"].items()}
        self.last_tick, self.rounds, self.seen, self.recent = (
            data["last_tick"],
            rounds,
            seen,
            recent,
        )


tracker = MatchTracker()
