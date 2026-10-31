"""BF1 对局：跟踪器每轮的驱动、落库与查询

全服统计每轮快照成功后在独立任务里跑一次 match_tracker，收尾的对局写两张表：bf1_rounds 每局
一行（含参与者 pid），bf1_player_round_days 每人每天一行，各局战绩条目按 round_stats 的紧凑
编码首尾相接追加。服务器的对局列表查前者；单局详情按 pid 列表取后者当天的行，挑出这一局的条目；
玩家的对局列表只读自己的行。数据保留 90 天。

开了武器载具（bf1_round_weapons）时，跟踪器把每人最近一次读到的完整生涯存进 bf1_career_snapshots
（保留 14 天），下次进服核心没变就沿用，不用重读武器类别。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import LargeBinary, Table, bindparam, cast, delete, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError
from app.core import ea_metrics
from app.core.cache import get_redis
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.domain.games.bf1 import round_awards as ra
from app.domain.games.bf1 import round_weapons as rw
from app.domain.games.bf1.blaze_catalog import catalog
from app.domain.games.bf1.blaze_stats import KITS
from app.domain.games.bf1.maps import (
    MapData,
    normalize_map_image_url,
    translate_map_name,
    translate_mode_name,
)
from app.domain.games.bf1.round_stats import (
    ACE_SQUAD,
    ASSISTS,
    COMBAT,
    DEATHS,
    DOGTAGS,
    ELITE,
    FINISHED,
    HEALS,
    KILLS,
    KIT_BASE,
    KIT_RANKS,
    LEFT_EARLY,
    LOSSES,
    MEDALS,
    MODE_SCORES,
    MVP,
    OBJECTIVE,
    RANK,
    RECORDS,
    REPAIRS,
    REVIVES,
    SCORE,
    SCORE_PARTS,
    SKILL,
    VEHICLE_KILLS,
    WINS,
    Entry,
    decode_entries,
    encode_entry,
    pack_pids,
    pack_vector,
    unpack_pids,
    unpack_vector,
)
from app.models.bf1.game_instance import Bf1GameInstance
from app.models.bf1.rounds import Bf1CareerSnapshot, Bf1PlayerRoundDay, Bf1Round
from app.schemas.bf1.rounds import (
    PlayerRound,
    PlayerRoundPage,
    RoundDetail,
    RoundPage,
    RoundPlayer,
    RoundRibbon,
    RoundScoreParts,
    RoundStar,
    RoundSummary,
    RoundWeapon,
)
from app.schemas.bf1.server import ServerSummary
from app.services.bf1.blaze_service import fetch_stats
from app.services.bf1.match_tracker import MAX_GAP, ClosedRound, MatchTracker, Snapshot
from app.services.bf1.match_tracker import tracker as default_tracker
from app.services.bf1.server_player_count_service import server_game_ids
from app.services.bf1.server_roster_service import Rosters, insert_for, read_names

RETENTION = timedelta(days=90)
SNAPSHOT_RETENTION = timedelta(days=14)
WRITE_CHUNK = 2000


def _day(ts: int) -> date:
    return datetime.fromtimestamp(ts, UTC).date()


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def _ts(dt: datetime) -> int:
    # sqlite 读回的是无时区时间，按写入时的 UTC 补上
    return int(dt.replace(tzinfo=dt.tzinfo or UTC).timestamp())


def _count_honors(c: ClosedRound) -> None:
    """核对游戏评的荣誉：实测每次结算 MVP 正好 1 人、王牌小队正好 5 人，对不上的局记下来。"""
    done = [ln.delta for ln in c.lines if ln.status == FINISHED]
    mvp = sum(1 for d in done if d[MVP])
    ace = sum(1 for d in done if d[ACE_SQUAD])
    ea_metrics.count_event(f"round_mvp_{min(mvp, 2)}")
    ea_metrics.count_event(
        "round_ace_5" if ace == 5 else f"round_ace_{'0' if not ace else 'other'}"
    )


async def save_rounds(db: AsyncSession, closed: list[ClosedRound]) -> int:
    """写入收尾的对局并提交，返回写入局数。"""
    entries: dict[tuple[int, date], bytes] = {}
    for c in closed:
        row = Bf1Round(
            game_id=c.game_id,
            map_name=c.map_name,
            game_mode=c.game_mode,
            started_at=_dt(c.started_at),
            ended_at=_dt(c.ended_at),
            observed_start=c.observed_start,
            settled=c.settled,
            winner=c.winner,
            player_count=len(c.lines),
            pids=pack_pids([ln.pid for ln in c.lines]),
        )
        db.add(row)
        await db.flush()
        if c.settled:
            _count_honors(c)
        day = _day(c.ended_at)
        for ln in c.lines:
            key = (ln.pid, day)
            entries[key] = entries.get(key, b"") + encode_entry(
                row.id, ln.team, ln.status, ln.delta, ln.weapons, ln.awards, ln.stars
            )
    rows = [{"pid": p, "day": d, "data": data} for (p, d), data in entries.items()]
    for i in range(0, len(rows), WRITE_CHUNK):
        stmt = insert_for(db, Bf1PlayerRoundDay).values(rows[i : i + WRITE_CHUNK])
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["pid", "day"],
                # 二进制的 + 不会编译成 ||，显式写运算符。sqlite 的 || 把 blob 当文本拼，再转回
                # blob；Postgres 里 bytea || bytea 本来就是 bytea
                set_={
                    "data": cast(Bf1PlayerRoundDay.data.op("||")(stmt.excluded.data), LargeBinary)
                },
            )
        )
    await db.commit()
    return len(closed)


async def purge_expired(db: AsyncSession, now: datetime) -> None:
    cutoff = now - RETENTION
    await db.execute(delete(Bf1Round).where(Bf1Round.ended_at < cutoff))
    await db.execute(delete(Bf1PlayerRoundDay).where(Bf1PlayerRoundDay.day < cutoff.date()))
    await db.execute(
        delete(Bf1CareerSnapshot).where(Bf1CareerSnapshot.updated_at < now - SNAPSHOT_RETENTION)
    )
    await db.commit()


class SnapshotStore:
    """跟踪器的生涯快照存储，落在 bf1_career_snapshots；每次 save 单独提交。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def load(self, pids: list[int]) -> dict[int, Snapshot]:
        out: dict[int, Snapshot] = {}
        for i in range(0, len(pids), WRITE_CHUNK):
            rows = await self.db.execute(
                select(
                    Bf1CareerSnapshot.pid,
                    Bf1CareerSnapshot.core,
                    Bf1CareerSnapshot.weapons,
                    Bf1CareerSnapshot.updated_at,
                ).where(Bf1CareerSnapshot.pid.in_(pids[i : i + WRITE_CHUNK]))
            )
            for pid, core, weapons, at in rows.tuples():
                out[pid] = (unpack_vector(core), weapons, _ts(at))
        return out

    async def save(self, snapshots: dict[int, Snapshot]) -> None:
        rows = [
            {"pid": pid, "core": pack_vector(vec), "weapons": blob, "updated_at": _dt(at)}
            for pid, (vec, blob, at) in snapshots.items()
        ]
        for i in range(0, len(rows), WRITE_CHUNK):
            stmt = insert_for(self.db, Bf1CareerSnapshot).values(rows[i : i + WRITE_CHUNK])
            await self.db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["pid"],
                    set_={
                        "core": stmt.excluded.core,
                        "weapons": stmt.excluded.weapons,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
            )
        await self.db.commit()

    async def load_awards(self, pids: list[int]) -> dict[int, tuple[bytes, int]]:
        out: dict[int, tuple[bytes, int]] = {}
        for i in range(0, len(pids), WRITE_CHUNK):
            rows = await self.db.execute(
                select(
                    Bf1CareerSnapshot.pid, Bf1CareerSnapshot.awards, Bf1CareerSnapshot.updated_at
                ).where(
                    Bf1CareerSnapshot.pid.in_(pids[i : i + WRITE_CHUNK]),
                    Bf1CareerSnapshot.awards.is_not(None),
                )
            )
            for pid, awards, at in rows.tuples():
                if awards is not None:
                    out[pid] = (awards, _ts(at))
        return out

    async def save_awards(self, snapshots: dict[int, bytes]) -> None:
        # 只更新已有的行：快照行要有核心和武器载具，没读到武器的人这次不存勋带
        # 用表而不是 ORM 实体：ORM 的批量 UPDATE 只认按主键，不接受自定义 WHERE
        table: Table = Bf1CareerSnapshot.__table__  # type: ignore[assignment]
        stmt = (
            update(table)
            .where(table.c.pid == bindparam("b_pid"))
            .values(awards=bindparam("b_awards"))
        )
        rows = [{"b_pid": pid, "b_awards": blob} for pid, blob in snapshots.items()]
        for i in range(0, len(rows), WRITE_CHUNK):
            await self.db.execute(stmt, rows[i : i + WRITE_CHUNK])
        await self.db.commit()


# 一轮查询加落库通常几秒；慢过一轮时跳过新的一轮，不排队，免得名单差分错位
_tick_lock = asyncio.Lock()
# 过期清理每个 UTC 日跑一次，记下上次跑的日期
_purged_on: dict[str, date] = {}
# 停机时把跟踪器状态存在这里，新进程启动时取走；断档超过 MAX_GAP 的状态本来也会被丢弃，键随之过期
STATE_KEY = "bfm:bf1:match_tracker_state"
# 停机时最多等这么久让进行中的一轮跑完，等不到就不存
SAVE_WAIT = 5


async def run_match_tick(
    summaries: list[ServerSummary],
    rosters: Rosters,
    *,
    tracker: MatchTracker | None = None,
) -> None:
    """全服统计每轮快照成功后调用：跑一轮对局跟踪并落库。异常只记日志。"""
    settings = get_settings()
    if not settings.bf1_match_tracking or _tick_lock.locked():
        return
    ea_metrics.set_source("tracker")
    t = tracker or default_tracker
    maps = {int(s.game_id): (s.map_name, s.game_mode) for s in summaries if s.game_id}
    now = datetime.now(UTC)
    try:
        async with _tick_lock, get_sessionmaker()() as db:

            async def fetch(
                pids: list[int], names: dict[str, list[str]]
            ) -> dict[int, dict[str, float]]:
                return await fetch_stats(db, pids, names)

            store = SnapshotStore(db) if settings.bf1_round_weapons else None
            closed = await t.tick(rosters, maps, int(now.timestamp()), fetch, store)
            if closed:
                await save_rounds(db, closed)
                logger.info(
                    "BF1 rounds saved: {} rounds, {} lines",
                    len(closed),
                    sum(len(c.lines) for c in closed),
                )
            if _purged_on.get("day") != now.date():
                await purge_expired(db, now)
                _purged_on["day"] = now.date()
    except Exception as e:
        logger.warning("BF1 match tick failed: {}", e)


async def _servers(db: AsyncSession, game_ids: set[int]) -> dict[int, tuple[str, int]]:
    """各 gameId 的服名和这台服最近一次出现的 gameId（没解析到 serverId 的就是它自己）。"""
    if not game_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(
                    Bf1GameInstance.game_id, Bf1GameInstance.name, Bf1GameInstance.server_id
                ).where(Bf1GameInstance.game_id.in_(game_ids))
            )
        )
        .tuples()
        .all()
    )
    server_ids = {sid for _, _, sid in rows if sid}
    latest: dict[int, int] = {}
    if server_ids:
        for sid, gid in (
            await db.execute(
                select(Bf1GameInstance.server_id, Bf1GameInstance.game_id)
                .where(Bf1GameInstance.server_id.in_(server_ids))
                .order_by(Bf1GameInstance.last_seen.desc())
            )
        ).tuples():
            latest.setdefault(sid, gid)
    return {gid: (name, latest.get(sid, gid) if sid else gid) for gid, name, sid in rows}


def _summary(r: Bf1Round, servers: dict[int, tuple[str, int]]) -> RoundSummary:
    teams = MapData.MapTeamDict.get(r.map_name or "") or {}
    server_name, server_game_id = servers.get(r.game_id, (None, r.game_id))
    return RoundSummary(
        id=r.id,
        game_id=r.game_id,
        server_game_id=server_game_id,
        server_name=server_name,
        map_name=r.map_name,
        map_display_name=translate_map_name(r.map_name),
        map_image_url=normalize_map_image_url(MapData.MapImageDict.get(r.map_name or "")),
        game_mode=r.game_mode,
        mode_display_name=translate_mode_name(r.game_mode),
        started_at=_ts(r.started_at),
        ended_at=_ts(r.ended_at),
        observed_start=r.observed_start,
        settled=r.settled,
        winner=r.winner if r.winner in (1, 2) else None,  # type: ignore[arg-type]
        team1_faction=teams.get("Team1"),
        team2_faction=teams.get("Team2"),
        player_count=r.player_count,
    )


def _item(key: str) -> tuple[str, dict[str, Any]]:
    """条目键（w:代号 / v:代号）→ (weapon / vehicle, 目录条目)"""
    prefix, code = key.split(":", 1)
    kind, name = ("weapon", "weapons") if prefix == "w" else ("vehicle", "vehicles")
    return kind, catalog(name).get(code) or {}


def _weapons(slots: dict[int, int] | None) -> list[RoundWeapon] | None:
    """武器载具槽位增量 → 按条目合并的列表，击杀多的在前、其次时长。"""
    if slots is None:
        return None
    by_item: dict[str, dict[str, int]] = {}
    for slot, v in slots.items():
        key, metric = rw.slot_item(slot)
        by_item.setdefault(key, {})[metric] = v
    out: list[RoundWeapon] = []
    for key, metrics in by_item.items():
        kind, entry = _item(key)
        out.append(
            RoundWeapon(
                kind=kind,  # type: ignore[arg-type]
                name=entry.get("name"),
                category=entry.get("category"),
                image=normalize_map_image_url(entry.get("image")),
                shared_kills=key in rw.SHARED_KILLS,
                **metrics,
            )
        )
    out.sort(key=lambda w: (-w.kills, -w.seconds))
    return out


def _stars(stars: dict[int, int]) -> list[RoundStar]:
    out = []
    for idx, n in stars.items():
        kind, entry = _item(rw.items()[idx])
        out.append(
            RoundStar(
                kind=kind,  # type: ignore[arg-type]
                name=entry.get("name"),
                image=normalize_map_image_url(entry.get("image")),
                stars=n,
            )
        )
    out.sort(key=lambda s: -s.stars)
    return out


def _score_parts(stats: dict[int, int], score: int) -> RoundScoreParts | None:
    """得分构成；一项分项都没有说明是 2026-11 之前记的条目（或这局 0 分），给 None。"""
    parts = {k: stats.get(i, 0) for k, i in SCORE_PARTS.items() if k != "xp"}
    objective = sum(stats.get(i, 0) for i in MODE_SCORES)
    if not objective and not any(parts.values()):
        return None
    return RoundScoreParts(
        objective=objective,
        other=score - objective - sum(parts.values()),
        **parts,
    )


def _player(pid: int, e: Entry, name: str | None) -> RoundPlayer:
    team, status, stats = e.team, e.status, e.stats
    kit_seconds = {kit: stats.get(KIT_BASE + 3 * i + 2, 0) for i, kit in enumerate(KITS)} | {
        "elite": stats.get(ELITE, 0)
    }
    seconds = sum(kit_seconds.values())
    kit = max(kit_seconds, key=lambda k: kit_seconds[k]) if seconds else None
    kills, deaths, score = stats.get(KILLS, 0), stats.get(DEATHS, 0), stats.get(SCORE, 0)
    won = None
    if status == FINISHED:
        won = True if stats.get(WINS) else False if stats.get(LOSSES) else None
    parts = _score_parts(stats, score)
    battle = score - parts.award - parts.bonus if parts is not None else None
    finished = status == FINISHED
    return RoundPlayer(
        persona_id=pid,
        name=name,
        team=team,  # type: ignore[arg-type]
        status="finished" if status == FINISHED else "left" if status == LEFT_EARLY else "suspect",
        won=won,
        kills=kills,
        deaths=deaths,
        score=score,
        assists=stats.get(ASSISTS, 0),
        revives=stats.get(REVIVES, 0),
        heals=stats.get(HEALS, 0),
        repairs=stats.get(REPAIRS, 0),
        dogtags=stats.get(DOGTAGS, 0),
        vehicle_kills=stats.get(VEHICLE_KILLS, 0),
        seconds=seconds,
        kit=kit,
        kd=round(kills / max(deaths, 1), 2),  # 没死过时 KD 记为击杀数
        kpm=round(kills / seconds * 60, 2) if seconds else None,
        spm=round((score if battle is None else battle) / seconds * 60) if seconds else None,
        weapons=_weapons(e.weapons),
        battle_score=battle,
        score_parts=parts,
        mvp=finished and stats.get(MVP, 0) > 0,
        ace_squad=finished and stats.get(ACE_SQUAD, 0) > 0,
        ribbons=None
        if e.awards is None
        else [
            RoundRibbon(code=ra.code(n), count=c)
            for n, c in sorted(e.awards.items(), key=lambda x: (-x[1], x[0]))
        ],
        medals=stats.get(MEDALS, 0),
        objective={k: v for k, i in OBJECTIVE.items() if (v := stats.get(i, 0))},
        combat={k: v for k, i in COMBAT.items() if (v := stats.get(i, 0))},
        rank_to=stats.get(RANK) or None,
        kit_ranks=[kit for kit, i in KIT_RANKS.items() if stats.get(i)],
        skill_delta=stats[SKILL] / 10 if stats.get(SKILL) else None,
        records={k: v for k, i in RECORDS.items() if (v := stats.get(i, 0))},
        stars=_stars(e.stars),
    )


async def list_server_rounds(
    db: AsyncSession, game_id: int, *, before: int | None = None, limit: int = 30
) -> RoundPage:
    """某服（重启前后的实例合在一起）结束时间在 before 之前的对局，按结束时间倒序。"""
    game_ids = await server_game_ids(db, game_id)
    cond = Bf1Round.game_id.in_(game_ids)
    if before is not None:
        cond &= Bf1Round.ended_at < _dt(before)
    rows = list(
        await db.scalars(
            select(Bf1Round).where(cond).order_by(Bf1Round.ended_at.desc()).limit(limit + 1)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    servers = await _servers(db, {r.game_id for r in rows})
    items = [_summary(r, servers) for r in rows]
    return RoundPage(items=items, next_before=items[-1].ended_at if more and items else None)


async def get_round(db: AsyncSession, round_id: int) -> RoundDetail:
    r = await db.get(Bf1Round, round_id)
    if r is None:
        raise NotFoundError(resource=f"对局 {round_id}")
    pids = unpack_pids(r.pids)
    day = _day(_ts(r.ended_at))
    rows = await db.execute(
        select(Bf1PlayerRoundDay.pid, Bf1PlayerRoundDay.data).where(
            tuple_(Bf1PlayerRoundDay.pid, Bf1PlayerRoundDay.day).in_([(p, day) for p in pids])
        )
    )
    names = await read_names(db, pids) if pids else {}
    players: list[RoundPlayer] = []
    for pid, data in rows.tuples():
        for e in decode_entries(data):
            if e.round_id == round_id:
                players.append(_player(pid, e, names.get(pid)))
    players.sort(key=lambda p: (p.team, -(p.score if p.battle_score is None else p.battle_score)))
    mvps = [p.persona_id for p in players if p.mvp]
    return RoundDetail(
        **_summary(r, await _servers(db, {r.game_id})).model_dump(),
        players=players,
        mvp_pid=mvps[0] if len(mvps) == 1 else None,
        ace_squad_pids=[p.persona_id for p in players if p.ace_squad],
    )


async def list_player_rounds(
    db: AsyncSession, persona_id: int, *, before: int | None = None, limit: int = 20
) -> PlayerRoundPage:
    """某玩家的对局，按对局 id（即结束先后）倒序；before 为上一页最后一局的 id。"""
    rows = await db.execute(
        select(Bf1PlayerRoundDay.data).where(Bf1PlayerRoundDay.pid == persona_id)
    )
    entries = sorted(
        (e for (data,) in rows.tuples() for e in decode_entries(data)),
        key=lambda e: -e.round_id,
    )
    if before is not None:
        entries = [e for e in entries if e.round_id < before]
    page, more = entries[:limit], len(entries) > limit
    rounds = {
        r.id: r
        for r in await db.scalars(
            select(Bf1Round).where(Bf1Round.id.in_([e.round_id for e in page]))
        )
    }
    servers = await _servers(db, {r.game_id for r in rounds.values()})
    name = (await read_names(db, [persona_id])).get(persona_id)
    items = [
        PlayerRound(
            round=_summary(rounds[e.round_id], servers), player=_player(persona_id, e, name)
        )
        for e in page
        if e.round_id in rounds
    ]
    return PlayerRoundPage(items=items, next_before=page[-1].round_id if more and page else None)


async def save_tracker_state(*, tracker: MatchTracker | None = None) -> None:
    """停机时导出跟踪器状态。部署重启一般一两分钟，新进程接着跟，不用全服重查基线、也不丢进行中的局。"""
    t = tracker or default_tracker
    if t.last_tick is None:
        return
    try:
        async with asyncio.timeout(SAVE_WAIT), _tick_lock:
            data = json.dumps(t.dump(), separators=(",", ":"))
        r = await get_redis()
        await r.set(STATE_KEY, data, ex=MAX_GAP)
        logger.info("BF1 match tracker state saved: {} rounds, {} bytes", len(t.rounds), len(data))
    except Exception as e:
        logger.warning("BF1 match tracker state not saved: {}", e)


async def restore_tracker_state(*, tracker: MatchTracker | None = None) -> None:
    """启动时取回上一个进程存下的状态（取走即删）；太旧或解析失败就从头开始。"""
    t = tracker or default_tracker
    try:
        r = await get_redis()
        raw = await r.getdel(STATE_KEY)
        if not raw:
            return
        data = json.loads(raw)
        age = int(datetime.now(UTC).timestamp()) - int(data["last_tick"])
        if age > MAX_GAP:
            logger.info("BF1 match tracker state too old ({}s), starting fresh", age)
            return
        t.load(data)
        logger.info(
            "BF1 match tracker state restored: {} rounds, {} seats, {}s old",
            len(t.rounds),
            sum(len(rnd.seats) for rnd in t.rounds.values()),
            age,
        )
    except Exception as e:
        logger.warning("BF1 match tracker state not restored: {}", e)
