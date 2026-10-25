"""BF1 私服人数与地图时序

全服统计每 60 秒拿到一轮快照摘要，这里每分钟为其中所有私服各写一个点（人数 + 当前地图 /
模式），并清理超过保留期的旧点；服务器详情页据此画 24 小时人数曲线，地图字段留给热门地图统计。

快照只有随重启变化的 gameId，稳定的 RSP serverId 要拿 gameId 问 Gateway。解析结果按 gameId
缓存，同一局只问一次，所以除首轮外只有服务器重启后才会产生请求。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.core.cache import get_cache
from app.domain.games.bf1.maps import (
    MapData,
    normalize_map_image_url,
    translate_map_name,
    translate_mode_name,
)
from app.models.bf1.server_player_count import Bf1ServerPlayerCount
from app.models.server import Server
from app.schemas.bf1.server import ServerMapStat, ServerPlayerCountPoint, ServerSummary
from app.services.bf1.server_service import BF1ServerService

RETENTION = timedelta(days=7)
# 每轮轮询采一次；留 10 秒余量，免得轮询抖动把间隔拖成 2 分钟。同一轮被重复触发时只记一次
SAMPLE_INTERVAL = timedelta(minutes=1) - timedelta(seconds=10)

SERVER_ID_CACHE_KEY = "bf1:gid_server_id:{}"
# 号池只有两三个号，首轮 150 多个私服分批解析，约 15 分钟解析完
RESOLVE_PER_ROUND = 10
SERVER_ID_TTL = int(timedelta(days=3).total_seconds())
# 查不到 serverId（EA 没返回 rspInfo）的局隔一小时再试，免得每轮都占名额
MISSING_SERVER_ID_TTL = int(timedelta(hours=1).total_seconds())


def _is_private(s: ServerSummary) -> bool:
    return not s.is_official and bool(s.game_id) and bool(s.name)


async def resolve_server_ids(db: AsyncSession, summaries: list[ServerSummary]) -> dict[int, int]:
    """返回本轮私服的 gameId → serverId。

    先查缓存，未命中的每轮最多问 Gateway RESOLVE_PER_ROUND 个；新解析到的顺手回填这一局已写的
    采样点，并把登记表里同一 serverId 的 game_id 更新成当前这一局。
    """
    cache = await get_cache()
    resolved: dict[int, int] = {}
    budget = RESOLVE_PER_ROUND
    for s in filter(_is_private, summaries):
        gid = int(s.game_id or 0)
        key = SERVER_ID_CACHE_KEY.format(gid)
        cached = await cache.get(key)
        if cached is not None:
            if cached:
                resolved[gid] = int(cached)
            continue
        if budget == 0:
            continue
        budget -= 1
        try:
            identity = await BF1ServerService(db).get_admin_identity(gid)
        except EAApiError as e:
            logger.warning("BF1 serverId resolve failed, retry next round: {}", e)
            break
        server_id = identity[2] if identity else None
        await cache.set(
            key, server_id or 0, ttl=SERVER_ID_TTL if server_id else MISSING_SERVER_ID_TTL
        )
        if not server_id:
            continue
        resolved[gid] = server_id
        await db.execute(
            update(Bf1ServerPlayerCount)
            .where(Bf1ServerPlayerCount.game_id == gid, Bf1ServerPlayerCount.server_id.is_(None))
            .values(server_id=server_id)
        )
        await db.execute(
            update(Server)
            .where(Server.game == "bf1", Server.server_id == server_id)
            .values(game_id=gid)
        )
    await db.commit()
    return resolved


async def record_player_counts(
    db: AsyncSession, summaries: list[ServerSummary], server_ids: dict[int, int] | None = None
) -> int:
    """距上次采样满 1 分钟时，为本轮所有私服写一个点并清理过期点，返回写入条数。"""
    now = datetime.now(UTC)
    last = await db.scalar(select(func.max(Bf1ServerPlayerCount.sampled_at)))
    # sqlite 读回的是无时区时间，按写入时的 UTC 补上
    if last is not None and now - last.replace(tzinfo=last.tzinfo or UTC) < SAMPLE_INTERVAL:
        return 0
    rows = [
        Bf1ServerPlayerCount(
            game_id=s.game_id,
            server_id=(server_ids or {}).get(int(s.game_id or 0)),
            name=s.name,
            map_name=s.map_name,
            game_mode=s.game_mode,
            player_count=s.player_count,
            queue_count=s.queue_count,
            spectator_count=s.spectator_count,
            max_player_count=s.max_player_count,
            sampled_at=now,
        )
        for s in summaries
        if _is_private(s)
    ]
    db.add_all(rows)
    await db.execute(
        delete(Bf1ServerPlayerCount).where(Bf1ServerPlayerCount.sampled_at < now - RETENTION)
    )
    await db.commit()
    return len(rows)


async def _server_rows(
    db: AsyncSession, game_id: int, since: datetime
) -> list[Bf1ServerPlayerCount]:
    """某私服 since 之后的采样点，按时间升序。

    先由 game_id 找到这个服最近一个点，解析到了 serverId 就按它取点（重启、改名都不影响）；
    还没解析到时退回按服名取点。同一时刻有多个同名私服时（生产上真有），只取本 game_id 的点，
    分不清归属的时刻跳过。
    """
    latest = await db.scalar(
        select(Bf1ServerPlayerCount)
        .where(Bf1ServerPlayerCount.game_id == game_id)
        .order_by(Bf1ServerPlayerCount.sampled_at.desc())
        .limit(1)
    )
    if latest is None:
        return []
    same_server = (
        Bf1ServerPlayerCount.server_id == latest.server_id
        if latest.server_id
        else Bf1ServerPlayerCount.name == latest.name
    )
    rows = await db.scalars(
        select(Bf1ServerPlayerCount)
        .where(same_server, Bf1ServerPlayerCount.sampled_at >= since)
        .order_by(Bf1ServerPlayerCount.sampled_at)
    )
    by_time: dict[datetime, list[Bf1ServerPlayerCount]] = {}
    for row in rows:
        by_time.setdefault(row.sampled_at, []).append(row)
    picked = []
    for same_time in by_time.values():
        own = [r for r in same_time if r.game_id == game_id]
        if own or len(same_time) == 1:
            picked.append((own or same_time)[0])
    return picked


def _ts(row: Bf1ServerPlayerCount) -> int:
    # sqlite 读回的是无时区时间，按写入时的 UTC 补上
    return int(row.sampled_at.replace(tzinfo=row.sampled_at.tzinfo or UTC).timestamp())


async def list_player_counts(
    db: AsyncSession, game_id: int, *, hours: int = 24
) -> list[ServerPlayerCountPoint]:
    """某私服最近 hours 小时的人数点（附当时地图 / 模式），按时间升序。"""
    rows = await _server_rows(db, game_id, datetime.now(UTC) - timedelta(hours=hours))
    return [
        ServerPlayerCountPoint(
            ts=_ts(p),
            players=p.player_count,
            queue=p.queue_count,
            spectators=p.spectator_count,
            max_players=p.max_player_count,
            map_name=p.map_name,
            game_mode=p.game_mode,
        )
        for p in rows
    ]


# 单个点最多代表这么久：相邻点间隔更长说明中间服务器空了（空服不采样），不计入地图时长
MAX_SAMPLE_SPAN = 120
# 间隔超过这么久就算新一轮，哪怕前后是同一张图
NEW_ROUND_GAP = 600


async def list_map_stats(db: AsyncSession, game_id: int, *, days: int = 7) -> list[ServerMapStat]:
    """某私服最近 days 天各地图的累计时长、人·分钟、平均人数与轮次，按人·分钟降序。

    时长按相邻采样点的时间差累加（单点封顶 MAX_SAMPLE_SPAN 秒），轮次按「地图或模式变化、
    或中断超过 NEW_ROUND_GAP 秒」切段计数。
    """
    rows = await _server_rows(db, game_id, datetime.now(UTC) - timedelta(days=days))
    stats: dict[tuple[str, str | None], dict[str, int]] = {}
    prev_key: tuple[str, str | None] | None = None
    prev_ts = 0
    for i, row in enumerate(rows):
        ts = _ts(row)
        next_ts = _ts(rows[i + 1]) if i + 1 < len(rows) else ts + 60
        span = min(next_ts - ts, MAX_SAMPLE_SPAN)
        if not row.map_name:
            prev_key = None
            continue
        key = (row.map_name, row.game_mode)
        st = stats.setdefault(key, {"seconds": 0, "player_seconds": 0, "rounds": 0, "last": 0})
        if key != prev_key or ts - prev_ts > NEW_ROUND_GAP:
            st["rounds"] += 1
        st["seconds"] += span
        st["player_seconds"] += span * row.player_count
        st["last"] = ts
        prev_key, prev_ts = key, ts
    result = [
        ServerMapStat(
            map_name=map_name,
            game_mode=mode,
            map_display_name=translate_map_name(map_name),
            mode_display_name=translate_mode_name(mode),
            map_image_url=normalize_map_image_url(MapData.MapImageDict.get(map_name)),
            minutes=round(st["seconds"] / 60),
            player_minutes=round(st["player_seconds"] / 60),
            avg_players=round(st["player_seconds"] / st["seconds"], 1) if st["seconds"] else 0.0,
            rounds=st["rounds"],
            last_seen=st["last"],
        )
        for (map_name, mode), st in stats.items()
    ]
    return sorted(result, key=lambda m: m.player_minutes, reverse=True)
