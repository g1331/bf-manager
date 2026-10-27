"""BF1 对局：跟踪器每轮的驱动、落库与查询

全服统计每轮快照成功后在独立任务里跑一次 match_tracker，收尾的对局写两张表：bf1_rounds 每局
一行（含参与者 pid），bf1_player_round_days 每人每天一行，各局战绩条目按 round_stats 的紧凑
编码首尾相接追加。服务器的对局列表查前者；单局详情按 pid 列表取后者当天的行，挑出这一局的条目；
玩家的对局列表只读自己的行。数据保留 90 天。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import LargeBinary, cast, delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.domain.games.bf1.blaze_stats import KITS
from app.domain.games.bf1.maps import (
    MapData,
    normalize_map_image_url,
    translate_map_name,
    translate_mode_name,
)
from app.domain.games.bf1.round_stats import (
    ASSISTS,
    DEATHS,
    DOGTAGS,
    ELITE,
    FINISHED,
    HEALS,
    KILLS,
    KIT_BASE,
    LEFT_EARLY,
    LOSSES,
    REPAIRS,
    REVIVES,
    SCORE,
    VEHICLE_KILLS,
    WINS,
    decode_entries,
    encode_entry,
    pack_pids,
    unpack_pids,
)
from app.models.bf1.game_instance import Bf1GameInstance
from app.models.bf1.rounds import Bf1PlayerRoundDay, Bf1Round
from app.schemas.bf1.rounds import (
    PlayerRound,
    PlayerRoundPage,
    RoundDetail,
    RoundPage,
    RoundPlayer,
    RoundSummary,
)
from app.schemas.bf1.server import ServerSummary
from app.services.bf1.blaze_service import fetch_stats
from app.services.bf1.match_tracker import ClosedRound, MatchTracker
from app.services.bf1.match_tracker import tracker as default_tracker
from app.services.bf1.server_player_count_service import server_game_ids
from app.services.bf1.server_roster_service import Rosters, insert_for, read_names

RETENTION = timedelta(days=90)
WRITE_CHUNK = 2000


def _day(ts: int) -> date:
    return datetime.fromtimestamp(ts, UTC).date()


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def _ts(dt: datetime) -> int:
    # sqlite 读回的是无时区时间，按写入时的 UTC 补上
    return int(dt.replace(tzinfo=dt.tzinfo or UTC).timestamp())


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
        day = _day(c.ended_at)
        for ln in c.lines:
            key = (ln.pid, day)
            entries[key] = entries.get(key, b"") + encode_entry(
                row.id, ln.team, ln.status, ln.delta
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
    await db.commit()


# 一轮查询加落库通常几秒；慢过一轮时跳过新的一轮，不排队，免得名单差分错位
_tick_lock = asyncio.Lock()
# 过期清理每个 UTC 日跑一次，记下上次跑的日期
_purged_on: dict[str, date] = {}


async def run_match_tick(
    summaries: list[ServerSummary],
    rosters: Rosters,
    *,
    tracker: MatchTracker | None = None,
) -> None:
    """全服统计每轮快照成功后调用：跑一轮对局跟踪并落库。异常只记日志。"""
    if not get_settings().bf1_match_tracking or _tick_lock.locked():
        return
    t = tracker or default_tracker
    maps = {int(s.game_id): (s.map_name, s.game_mode) for s in summaries if s.game_id}
    now = datetime.now(UTC)
    try:
        async with _tick_lock, get_sessionmaker()() as db:

            async def fetch(
                pids: list[int], names: dict[str, list[str]]
            ) -> dict[int, dict[str, float]]:
                return await fetch_stats(db, pids, names)

            closed = await t.tick(rosters, maps, int(now.timestamp()), fetch)
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


async def _server_names(db: AsyncSession, game_ids: set[int]) -> dict[int, str]:
    if not game_ids:
        return {}
    rows = await db.execute(
        select(Bf1GameInstance.game_id, Bf1GameInstance.name).where(
            Bf1GameInstance.game_id.in_(game_ids)
        )
    )
    return dict(rows.tuples().all())


def _summary(r: Bf1Round, server_name: str | None) -> RoundSummary:
    teams = MapData.MapTeamDict.get(r.map_name or "") or {}
    return RoundSummary(
        id=r.id,
        game_id=r.game_id,
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


def _player(
    pid: int, team: int, status: int, stats: dict[int, int], name: str | None
) -> RoundPlayer:
    kit_seconds = {kit: stats.get(KIT_BASE + 3 * i + 2, 0) for i, kit in enumerate(KITS)} | {
        "elite": stats.get(ELITE, 0)
    }
    seconds = sum(kit_seconds.values())
    kit = max(kit_seconds, key=lambda k: kit_seconds[k]) if seconds else None
    kills, deaths, score = stats.get(KILLS, 0), stats.get(DEATHS, 0), stats.get(SCORE, 0)
    won = None
    if status == FINISHED:
        won = True if stats.get(WINS) else False if stats.get(LOSSES) else None
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
        kd=round(kills / deaths, 2) if deaths else None,
        kpm=round(kills / seconds * 60, 2) if seconds else None,
        spm=round(score / seconds * 60) if seconds else None,
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
    names = await _server_names(db, {r.game_id for r in rows})
    items = [_summary(r, names.get(r.game_id)) for r in rows]
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
        for rid, team, status, stats in decode_entries(data):
            if rid == round_id:
                players.append(_player(pid, team, status, stats, names.get(pid)))
    players.sort(key=lambda p: (p.team, -p.score))
    server = (await _server_names(db, {r.game_id})).get(r.game_id)
    return RoundDetail(
        **_summary(r, server).model_dump(),
        players=players,
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
        key=lambda e: -e[0],
    )
    if before is not None:
        entries = [e for e in entries if e[0] < before]
    page, more = entries[:limit], len(entries) > limit
    rounds = {
        r.id: r
        for r in await db.scalars(select(Bf1Round).where(Bf1Round.id.in_([e[0] for e in page])))
    }
    servers = await _server_names(db, {r.game_id for r in rounds.values()})
    name = (await read_names(db, [persona_id])).get(persona_id)
    items = [
        PlayerRound(
            round=_summary(rounds[rid], servers.get(rounds[rid].game_id)),
            player=_player(persona_id, team, status, stats, name),
        )
        for rid, team, status, stats in page
        if rid in rounds
    ]
    return PlayerRoundPage(items=items, next_before=page[-1][0] if more and page else None)
