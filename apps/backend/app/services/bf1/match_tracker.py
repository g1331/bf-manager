"""BF1 对局跟踪：每分钟随全服快照跑一轮，用生涯差分算出每局每人的战绩

依据（2026-10-27 实测，见 round_stats）：生涯只在结算和中途退出时写入。所以

- 有人进服（含开始跟踪时已经在服的人），查一次核心生涯作为基线；
- 有人离开，下一次查询拿到的就是他离开时写进去的值，即他这一局的终值；
- 每轮从每台服挑几个基线稳定的人只查「完成局数」，有一半以上 +1 就说明这台服结算了；
  等下一轮（约一分钟，让整服写完）再把在服的人全查一遍，作为这一局的终值、下一局的基线；
- 进服后过一阵复查一次局数和胜负：之前打过的局的结算可能在进服后几分钟才写入（实测从离线
  直接进服的人也有 3–4%），变了就重查全量换成新的基线，免得算进这一局；
- 刚从别的服过来、离开那台服之后已经查到过值的人，直接拿这个值当基线，不再重查；
- EA 没返回某人的数据时（多半是还没有生涯记录的号），隔 MISSING_RETRY 再查，不再每轮重查。

给了快照存储（store）时还记武器载具（见 round_weapons），同一轮分两段查：先查核心（顺带 STAT 里的
载具和冷门类别的哨兵），再给需要的人读武器类别。依据是 2026-10-28 的一小时实测：核心不变时武器载具
也不变（755 次武器变化只有 2 次例外，都是离开时分两段写入、核心 40 秒内跟上），所以

- 核心和最近一次的快照一样（不论是 10 分钟内查过、本局基线，还是存储里几天前的），直接沿用；
- 核心变了才读 player_weapons1–5；冷门的 statcategory3/4 再看哨兵，哨兵没变就沿用上次的值，
  按 AUDIT_EVERY 抽一部分跳过的人照读，核对哨兵；
- 读失败、超出每轮上限的人这一局没有武器载具数据（条目上不打 WITH_WEAPONS 位），核心照常记。

勋带（见 round_awards）是第三段，和武器载具一样跟着核心查询走，但互不牵连：核心里的「获得勋带数」
和勋带勋章奖励分都没变就沿用上次的勋带，变了才读 3 个勋带类别，按 AWARDS_AUDIT_EVERY 抽查；
读失败、超出 MAX_AWARDS_PER_TICK 的人这一局没有勋带数据（不打 WITH_AWARDS 位）。

2026-10-31 核心向量追加了统计项。追加前查到的基线、快照比现在短，差分和「核心没变」的判断都只看
共有的部分（round_stats.diff / same_core），新加的项在跨版本的那一局记 0。

状态在内存里，停机时导出、启动时导入（见 round_service），重启间隔不超过 MAX_GAP 就接着跟；
快照断档太久则从头开始，接手时已经开打的局标记为 observed_start=False。
查询经注入的 fetch 发出，本模块不碰数据库与网络，便于测试。各环节查了多少人记在 ea_metrics 的
跟踪器事件里，用来判断哪些查询可以省。
"""

from __future__ import annotations

import asyncio
import base64
import zlib
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from loguru import logger

from app.core import ea_metrics
from app.domain.games.bf1 import round_awards as ra
from app.domain.games.bf1 import round_weapons as rw
from app.domain.games.bf1.blaze_stats import STAT
from app.domain.games.bf1.round_stats import (
    FINISHED,
    KILLS,
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
    same_core,
    to_vector,
)
from app.services.bf1.server_roster_service import TEAM1, TEAM2, Rosters

Fetch = Callable[[list[int], dict[str, list[str]]], Awaitable[dict[int, dict[str, float]]]]
# 一个人某一时刻的生涯：核心向量、武器载具快照（round_weapons.pack）、时刻
Snapshot = tuple[list[int], bytes, int]


class SnapshotStore(Protocol):
    """每人最近一次的完整生涯，跨会话保留；进服时核心没变就沿用里面的武器载具，不用重读。"""

    async def load(self, pids: list[int]) -> dict[int, Snapshot]: ...

    async def save(self, snapshots: dict[int, Snapshot]) -> None: ...

    async def load_awards(self, pids: list[int]) -> dict[int, tuple[bytes, int]]:
        """每人最近一次的勋带快照和时刻"""
        ...

    async def save_awards(self, snapshots: dict[int, bytes]) -> None:
        """只更新已有快照行的勋带；还没有快照行的人不存"""
        ...


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
# 每轮最多查这么多人的核心生涯（每 256 人、每个类别一个请求，即 8 个请求）。刚启动时几千人都要
# 查基线，分几轮查完；平时每分钟进出、结算加复查约七百人
MAX_QUERY_PER_TICK = 1024
# 进服前这么久之内在别的服出现过，算换服过来的（可能带着上一台服迟到的结算）
HOP_WINDOW = 900
# 查到的向量留这么久，统计进服时有没有现成的值可当基线
VECTOR_KEEP = 600
# EA 没返回某人的数据时，隔这么久再查他的基线
MISSING_RETRY = 600
# 每轮最多给这么多人读武器类别（每 256 人每类一个请求）；超出的人这一局没有武器载具数据，结算、
# 离开和重查基线的人优先
MAX_WEAPONS_PER_TICK = 768
# 冷门类别哨兵没变时跳过不读，每这么多个跳过的人抽一个照读，核对哨兵有没有漏。轰炸机的哨兵
# 是现成的分类合计，2026-10-28/29 抽查 2.7 万次零遗漏，抽得稀一些
AUDIT_EVERY: dict[str, int] = {"player_statcategory3": 16, "player_statcategory4": 64}
# 每轮最多给这么多人读勋带类别，优先级同武器
MAX_AWARDS_PER_TICK = 768
# 勋带门控没变时跳过不读，每这么多个跳过的人抽一个照读
AWARDS_AUDIT_EVERY = 32

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
    retry_at: int | None = None  # EA 没返回数据，到这个时刻才再查基线
    base_w: bytes | None = None  # 和 base 同一时刻的武器载具快照，None 表示没有
    end_w: bytes | None = None  # 和 end 同一时刻的武器载具快照
    base_a: bytes | None = None  # 和 base 同一时刻的勋带快照，None 表示没有
    end_a: bytes | None = None


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
    weapons: dict[int, int] | None = None  # 武器载具槽位的非零增量；None 表示没有数据
    awards: dict[int, int] | None = None  # 勋带号的非零增量；None 表示没有数据
    stars: dict[int, int] = field(default_factory=dict)  # 本局拿到服役星的条目下标 → 新星数


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


def _stars(end_w: bytes, base_w: bytes) -> dict[int, int]:
    """击杀跨过整百的武器载具（每 100 杀一颗服役星，与前端 starsByKills 一致）→ 新的星数"""
    _, end = rw.unpack(end_w)
    _, base = rw.unpack(base_w)
    return {
        slot // len(rw.METRICS): k // 100
        for slot, k in end.items()
        if slot % len(rw.METRICS) == rw.KILLS_METRIC and k // 100 > base.get(slot, 0) // 100
    }


def _line(
    pid: int, seat: Seat, end: list[int], end_w: bytes | None, end_a: bytes | None
) -> RoundLine | None:
    if seat.base is None or seat.team == 0:
        return None
    delta = diff(end, seat.base)
    if delta is None or not any(delta):
        return None
    # 升级前离开时存下的终值比现在短：补齐，后面按下标取新统计项不会越界
    delta += [0] * (len(ROUND_STATS) - len(delta))
    rounds = delta[ROUNDS]
    status = FINISHED if rounds == 1 else LEFT_EARLY if rounds == 0 else SUSPECT
    weapons = None
    if seat.base_w is not None and end_w is not None:
        weapons = rw.diff(end_w, seat.base_w)
        if weapons is not None:
            # 对账：各武器载具击杀之和应等于核心击杀增量（目录不含的击杀方式会让它对不上）
            same = rw.kills(weapons) == delta[KILLS]
            ea_metrics.count_event("weapons_kills_match" if same else "weapons_kills_diff")
    awards = None
    if seat.base_a is not None and end_a is not None:
        awards = rw.diff(end_a, seat.base_a)
    stars = _stars(end_w, seat.base_w) if weapons is not None and end_w and seat.base_w else {}
    return RoundLine(pid, seat.team, status, delta, weapons, awards, stars)


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


@dataclass
class _Plan:
    """一个人这一轮要读的武器类别；沿用的类别从 prior 里拷，audits 是哨兵没变、抽中照读的类别"""

    cats: set[str]
    prior: dict[int, int]
    audits: set[str]


def _plan(pid: int, values: dict[str, float], prior: Snapshot | None, now: int) -> _Plan:
    """核心变了的人：武器 1–5 类都读；冷门类别哨兵变了才读，没变的按 AUDIT_EVERY 抽查。"""
    cats, audits = set(rw.ALWAYS), set()
    gates = rw.read_gates(values)
    prior_gates, prior_values = rw.unpack(prior[1]) if prior is not None else (None, {})
    for cat, sl in rw.GATE_SLICES.items():
        if prior_gates is None:
            cats.add(cat)
        elif prior_gates[sl] != gates[sl]:
            cats.add(cat)
            ea_metrics.count_event(f"weapons_gate_read_{cat[-1]}")
        elif zlib.crc32(f"{pid}:{now}:{cat}".encode()) % AUDIT_EVERY[cat] == 0:
            cats.add(cat)
            audits.add(cat)
        else:
            ea_metrics.count_event(f"weapons_gate_skip_{cat[-1]}")
    return _Plan(cats, prior_values, audits)


async def _fetch_categories(
    plans: dict[int, _Plan], fetch: Fetch
) -> dict[str, dict[int, dict[str, float]] | None]:
    """每个类别一次 fetch（内部再按 STATS_BATCH_SIZE 人分批），并发发出；失败的类别给 None。"""
    cats = sorted({c for plan in plans.values() for c in plan.cats})
    with ea_metrics.ea_source("tracker_weapons"):
        results = await asyncio.gather(
            *(
                fetch(
                    sorted(p for p, plan in plans.items() if cat in plan.cats),
                    rw.category_names(cat),
                )
                for cat in cats
            ),
            return_exceptions=True,
        )
    read: dict[str, dict[int, dict[str, float]] | None] = {}
    for cat, r in zip(cats, results, strict=True):
        if isinstance(r, BaseException):
            logger.warning("BF1 match tracker weapons query failed ({}): {}", cat, r)
            read[cat] = None
        else:
            read[cat] = r
    return read


def _merge(
    pid: int,
    values: dict[str, float],
    plan: _Plan,
    read: dict[str, dict[int, dict[str, float]] | None],
) -> bytes | None:
    """拼出快照：STAT 里的条目来自核心查询，读了的类别用新值，没读的沿用 prior；缺一类就放弃。"""
    merged = rw.read_slots(values, STAT) or {}
    for cat in (*rw.ALWAYS, *rw.GATES):
        if cat not in plan.cats:
            merged |= rw.in_category(plan.prior, cat)
            continue
        rows = read.get(cat)
        got = rw.read_slots(rows.get(pid, {}), cat) if rows is not None else None
        if got is None:
            return None
        if cat in plan.audits:
            same = got == rw.in_category(plan.prior, cat)
            ea_metrics.count_event(f"weapons_audit_{'ok' if same else 'miss'}_{cat[-1]}")
        merged |= got
    return rw.pack(rw.read_gates(values), merged)


def _plan_awards(
    vectors: dict[int, list[int]], priors: dict[int, tuple[bytes, int]], now: int
) -> tuple[dict[int, bytes], list[int], set[int]]:
    """门控没变的沿用上次的勋带（按 AWARDS_AUDIT_EVERY 抽一部分照读），其余要读。

    返回 (沿用的快照, 要读的人, 其中抽查的人)。
    """
    out: dict[int, bytes] = {}
    todo: list[int] = []
    audits: set[int] = set()
    for pid, vec in vectors.items():
        prior = priors.get(pid)
        if prior is None or rw.unpack(prior[0])[0] != ra.gates(vec):
            todo.append(pid)
        elif zlib.crc32(f"{pid}:{now}:awards".encode()) % AWARDS_AUDIT_EVERY == 0:
            todo.append(pid)
            audits.add(pid)
        else:
            out[pid] = prior[0]
            ea_metrics.count_event("awards_reused")
    return out, todo, audits


class MatchTracker:
    def __init__(self) -> None:
        self.rounds: dict[int, OpenRound] = {}
        self.last_tick: int | None = None
        # 每个人最近一次出现在哪台服、什么时候（只留 HOP_WINDOW 内的），判断进服是不是换服
        self.seen: dict[int, tuple[int, int]] = {}
        # 每个人最近查到的向量、时刻、武器载具快照和勋带快照（只留 VECTOR_KEEP 内的）
        self.recent: dict[int, tuple[list[int], int, bytes | None, bytes | None]] = {}

    async def tick(
        self,
        rosters: Rosters,
        maps: dict[int, tuple[str | None, str | None]],
        now: int,
        fetch: Fetch,
        store: SnapshotStore | None = None,
    ) -> list[ClosedRound]:
        """处理一轮快照名单，返回这一轮收尾的对局。查询失败时保留状态，下一轮重试。

        给了 store 才记武器载具。
        """
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
        weapons: dict[int, bytes] = {}
        awards: dict[int, bytes] = {}
        if wanted := self._wanted(now, settling):
            names = rw.full_names() if store is not None else round_stat_names()
            try:
                values = await fetch(sorted(wanted), names)
            except Exception as e:
                logger.warning("BF1 match tracker stats query failed, retry next round: {}", e)
                return closed
            vectors = {pid: to_vector(v) for pid, v in values.items()}
            if store is not None and vectors:
                urgent = self._urgent(vectors, settling)
                try:
                    weapons = await self._read_weapons(values, vectors, urgent, now, fetch, store)
                except Exception as e:
                    # 武器载具出任何问题都不能拖住核心战绩：这一轮的人只是没有武器载具数据
                    logger.warning("BF1 match tracker weapons stage failed: {}", e)
                try:
                    awards = await self._read_awards(vectors, urgent, now, fetch, store)
                except Exception as e:
                    logger.warning("BF1 match tracker awards stage failed: {}", e)
            self._apply(vectors, weapons, awards, now)
            self._back_off(wanted - vectors.keys(), now)

        for gid in list(self.rounds):
            rnd = self.rounds[gid]
            if gid in settling:
                closed.append(self._close(gid, rnd, vectors, weapons, awards, now, settled=True))
            elif gid not in rosters and all(s.left for s in rnd.seats.values()):
                # 服务器从快照里消失（关服、清空），没等到结算
                closed.append(self._close(gid, rnd, vectors, weapons, awards, now, settled=False))
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
                    seat.base_w, seat.base_a = recent[2], recent[3]
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
                    if s.retry_at is None or s.retry_at <= now:
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

    def _apply(
        self,
        vectors: dict[int, list[int]],
        weapons: dict[int, bytes],
        awards: dict[int, bytes],
        now: int,
    ) -> None:
        self.recent.update(
            (pid, (vec, now, weapons.get(pid), awards.get(pid))) for pid, vec in vectors.items()
        )
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                vec = vectors.get(pid)
                if vec is None:
                    continue
                w, a = weapons.get(pid), awards.get(pid)
                if s.base is None:
                    s.base, s.base_at, s.base_w, s.base_a = vec, now, w, a
                elif s.left and s.end is None:
                    s.end, s.end_w, s.end_a = vec, w, a
                elif s.rebase and rnd.settle_seen_at is None:
                    s.base, s.base_at, s.base_w, s.base_a, s.rebase = vec, now, w, a, False

    def _priors(self, pids: Iterable[int]) -> dict[int, Snapshot]:
        """内存里每人最近一次带武器载具的快照：10 分钟内查到的值，或在服席位的基线。"""
        want = set(pids)
        out: dict[int, Snapshot] = {}

        def offer(pid: int, vec: list[int], blob: bytes | None, at: int) -> None:
            if blob is not None and (pid not in out or at > out[pid][2]):
                out[pid] = (vec, blob, at)

        for pid in want:
            if (r := self.recent.get(pid)) is not None:
                offer(pid, r[0], r[2], r[1])
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                if pid in want and s.base is not None:
                    offer(pid, s.base, s.base_w, s.base_at)
        return out

    async def _read_weapons(
        self,
        values: dict[int, dict[str, float]],
        vectors: dict[int, list[int]],
        urgent: set[int],
        now: int,
        fetch: Fetch,
        store: SnapshotStore,
    ) -> dict[int, bytes]:
        """第二段：给本轮查了核心的人配上武器载具快照。读不到的人不在结果里。"""
        priors = self._priors(vectors)
        if unknown := sorted(vectors.keys() - priors.keys()):
            try:
                stored = await store.load(unknown)
            except Exception as e:
                logger.warning("BF1 match tracker snapshot store load failed: {}", e)
                stored = {}
            ea_metrics.count_event("weapons_store_hit", len(stored))
            priors.update(stored)
        self._count_joins(vectors, priors)

        out: dict[int, bytes] = {}
        plans: dict[int, _Plan] = {}
        for pid, vec in vectors.items():
            prior = priors.get(pid)
            if prior is not None and same_core(prior[0], vec):
                out[pid] = prior[1]
                ea_metrics.count_event("weapons_reused")
            else:
                plans[pid] = _plan(pid, values[pid], prior, now)
        if len(plans) > MAX_WEAPONS_PER_TICK:
            order = sorted(plans, key=lambda p: p not in urgent)
            for pid in order[MAX_WEAPONS_PER_TICK:]:
                del plans[pid]
            ea_metrics.count_event("weapons_skipped", len(order) - MAX_WEAPONS_PER_TICK)
        if not plans:
            return out

        read = await _fetch_categories(plans, fetch)
        ea_metrics.count_event("weapons_read", len(plans))
        saved: dict[int, Snapshot] = {}
        for pid, plan in plans.items():
            if (blob := _merge(pid, values[pid], plan, read)) is None:
                ea_metrics.count_event("weapons_failed")
                continue
            out[pid] = blob
            saved[pid] = (vectors[pid], blob, now)
        if saved:
            try:
                await store.save(saved)
            except Exception as e:
                logger.warning("BF1 match tracker snapshot store save failed: {}", e)
        return out

    def _urgent(self, vectors: dict[int, list[int]], settling: set[int]) -> set[int]:
        """本轮查了核心的人里要算终值或重查基线的，读武器、勋带时优先。"""
        return {
            pid
            for gid, rnd in self.rounds.items()
            for pid, s in rnd.seats.items()
            if pid in vectors
            and s.base is not None
            and ((not s.left and gid in settling) or (s.left and s.end is None) or s.rebase)
        }

    def _count_joins(self, vectors: dict[int, list[int]], priors: dict[int, Snapshot]) -> None:
        """进服基线和最近一次快照比，按没变 / 变了 / 没见过计数。"""
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                if pid not in vectors or s.base is not None:
                    continue
                prior = priors.get(pid)
                if prior is None:
                    ea_metrics.count_event("join_core_unseen")
                else:
                    same = same_core(prior[0], vectors[pid])
                    ea_metrics.count_event("join_core_same" if same else "join_core_changed")

    async def _read_awards(
        self,
        vectors: dict[int, list[int]],
        urgent: set[int],
        now: int,
        fetch: Fetch,
        store: SnapshotStore,
    ) -> dict[int, bytes]:
        """第三段：给本轮查了核心的人配上勋带快照。门控没变就沿用，读不到的人不在结果里。"""
        priors = await self._award_priors(vectors, store)
        out, todo, audits = _plan_awards(vectors, priors, now)
        if len(todo) > MAX_AWARDS_PER_TICK:
            todo.sort(key=lambda p: (p not in urgent, p in audits))
            for pid in todo[MAX_AWARDS_PER_TICK:]:
                if pid in audits:
                    out[pid] = priors[pid][0]  # 抽查名额被挤掉的照常沿用
            ea_metrics.count_event("awards_skipped", len(todo) - MAX_AWARDS_PER_TICK)
            todo = todo[:MAX_AWARDS_PER_TICK]
        if not todo:
            return out
        try:
            with ea_metrics.ea_source("tracker_awards"):
                rows = await fetch(sorted(todo), ra.names())
        except Exception as e:
            logger.warning("BF1 match tracker awards query failed: {}", e)
            ea_metrics.count_event("awards_failed", len(todo))
            return out
        ea_metrics.count_event("awards_read", len(todo))
        saved: dict[int, bytes] = {}
        for pid in todo:
            # 3 个类别分别请求、按人合并，缺了哪一类都不能当成 0 存下来
            if (counts := ra.read(rows.get(pid, {}))) is None:
                ea_metrics.count_event("awards_failed")
                continue
            blob = rw.pack(ra.gates(vectors[pid]), counts)
            if pid in audits:
                same = rw.unpack(blob)[1] == rw.unpack(priors[pid][0])[1]
                ea_metrics.count_event(f"awards_audit_{'ok' if same else 'miss'}")
            out[pid] = saved[pid] = blob
        if saved:
            try:
                await store.save_awards(saved)
            except Exception as e:
                logger.warning("BF1 match tracker awards store save failed: {}", e)
        return out

    async def _award_priors(
        self, vectors: dict[int, list[int]], store: SnapshotStore
    ) -> dict[int, tuple[bytes, int]]:
        """每人最近一次的勋带快照和时刻：内存里 10 分钟内查到的、在服席位的基线，没有再查存储。"""
        priors: dict[int, tuple[bytes, int]] = {}

        def offer(pid: int, blob: bytes | None, at: int) -> None:
            if blob is not None and (pid not in priors or at > priors[pid][1]):
                priors[pid] = (blob, at)

        for pid in vectors:
            if (r := self.recent.get(pid)) is not None:
                offer(pid, r[3], r[1])
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                if pid in vectors:
                    offer(pid, s.base_a, s.base_at)
        if unknown := sorted(vectors.keys() - priors.keys()):
            try:
                stored = await store.load_awards(unknown)
            except Exception as e:
                logger.warning("BF1 match tracker awards store load failed: {}", e)
                stored = {}
            ea_metrics.count_event("awards_store_hit", len(stored))
            priors.update(stored)
        return priors

    def _back_off(self, missing: set[int], now: int) -> None:
        """EA 没返回这些人的数据：还缺基线的隔 MISSING_RETRY 再查，免得每轮都查一遍。"""
        if not missing:
            return
        ea_metrics.count_event("stats_missing", len(missing))
        for rnd in self.rounds.values():
            for pid, s in rnd.seats.items():
                if pid in missing and s.base is None:
                    s.retry_at = now + MISSING_RETRY

    def _close(
        self,
        gid: int,
        rnd: OpenRound,
        vectors: dict[int, list[int]],
        weapons: dict[int, bytes],
        awards: dict[int, bytes],
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
            end_w = s.end_w if s.left else weapons.get(pid)
            end_a = s.end_a if s.left else awards.get(pid)
            if end is not None and (ln := _line(pid, s, end, end_w, end_a)) is not None:
                lines.append(ln)
            if not s.left:
                carry[pid] = (
                    Seat(
                        since=boundary,
                        team=s.team,
                        base=end,
                        base_at=now,
                        base_w=end_w,
                        base_a=end_a,
                    )
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
                    "seats": {str(pid): _seat_out(seat) for pid, seat in r.seats.items()},
                }
                for gid, r in self.rounds.items()
            },
            "seen": {str(pid): list(v) for pid, v in self.seen.items()},
            "recent": {
                str(pid): [vec, at, _b64(w), _b64(a)]
                for pid, (vec, at, w, a) in self.recent.items()
            },
        }

    def load(self, data: dict[str, Any]) -> None:
        """导入 dump 的结果；先全部解析完再替换，数据不对就抛错、原状态不动。"""
        rounds = {
            int(gid): OpenRound(
                started_at=r["started_at"],
                observed_start=r["observed_start"],
                settle_seen_at=r["settle_seen_at"],
                maps=Counter({(m, mode): n for m, mode, n in r["maps"]}),
                seats={int(pid): _seat_in(seat) for pid, seat in r["seats"].items()},
            )
            for gid, r in data["rounds"].items()
        }
        seen = {int(pid): (v[0], v[1]) for pid, v in data["seen"].items()}
        # 旧版本导出的 recent 没有武器载具、勋带快照
        recent = {
            int(pid): (
                v[0],
                v[1],
                _unb64(v[2] if len(v) > 2 else None),
                _unb64(v[3] if len(v) > 3 else None),
            )
            for pid, v in data["recent"].items()
        }
        self.last_tick, self.rounds, self.seen, self.recent = (
            data["last_tick"],
            rounds,
            seen,
            recent,
        )


def _b64(blob: bytes | None) -> str | None:
    return base64.b64encode(blob).decode() if blob is not None else None


def _unb64(text: str | None) -> bytes | None:
    return base64.b64decode(text) if text is not None else None


_SEAT_BLOBS = ("base_w", "end_w", "base_a", "end_a")


def _seat_out(seat: Seat) -> dict[str, Any]:
    d = asdict(seat)
    for k in _SEAT_BLOBS:
        d[k] = _b64(d[k])
    return d


def _seat_in(d: dict[str, Any]) -> Seat:
    return Seat(**{k: _unb64(v) if k in _SEAT_BLOBS else v for k, v in d.items()})


tracker = MatchTracker()
