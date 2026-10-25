"""BF1 私服人数与地图时序

全服统计每 60 秒拿到一轮快照摘要，这里每 5 分钟为其中所有私服各写一个点（人数 + 当前地图 /
模式），并清理超过保留期的旧点；服务器详情页据此画 24 小时人数曲线，地图字段留给热门地图统计。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bf1.server_player_count import Bf1ServerPlayerCount
from app.schemas.bf1.server import ServerPlayerCountPoint, ServerSummary

RETENTION = timedelta(days=7)
# 轮询每分钟一次，采样隔 5 分钟一次；留 10 秒余量，免得轮询抖动把采样拖到 10 分钟
SAMPLE_INTERVAL = timedelta(minutes=5) - timedelta(seconds=10)


async def record_player_counts(db: AsyncSession, summaries: list[ServerSummary]) -> int:
    """距上次采样满 5 分钟时，为本轮所有私服写一个点并清理过期点，返回写入条数。"""
    now = datetime.now(UTC)
    last = await db.scalar(select(func.max(Bf1ServerPlayerCount.sampled_at)))
    # sqlite 读回的是无时区时间，按写入时的 UTC 补上
    if last is not None and now - last.replace(tzinfo=last.tzinfo or UTC) < SAMPLE_INTERVAL:
        return 0
    rows = [
        Bf1ServerPlayerCount(
            game_id=s.game_id,
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
        if not s.is_official and s.game_id and s.name
    ]
    db.add_all(rows)
    await db.execute(
        delete(Bf1ServerPlayerCount).where(Bf1ServerPlayerCount.sampled_at < now - RETENTION)
    )
    await db.commit()
    return len(rows)


async def list_player_counts(
    db: AsyncSession, game_id: int, *, hours: int = 24
) -> list[ServerPlayerCountPoint]:
    """某私服最近 hours 小时的人数点，按时间升序。

    先由 game_id 找到这个服的名字，再按名字取点，服务器重启换了 gameId 曲线也能连上。
    shortcut: 按服名归并，改名后历史会断、同名私服会混在一起；快照能拿到稳定 serverId 再换键。
    """
    name = await db.scalar(
        select(Bf1ServerPlayerCount.name)
        .where(Bf1ServerPlayerCount.game_id == game_id)
        .order_by(Bf1ServerPlayerCount.sampled_at.desc())
        .limit(1)
    )
    if name is None:
        return []
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = await db.scalars(
        select(Bf1ServerPlayerCount)
        .where(Bf1ServerPlayerCount.name == name, Bf1ServerPlayerCount.sampled_at >= since)
        .order_by(Bf1ServerPlayerCount.sampled_at)
    )
    return [
        ServerPlayerCountPoint(
            # sqlite 读回的是无时区时间，按写入时的 UTC 补上
            ts=int(p.sampled_at.replace(tzinfo=p.sampled_at.tzinfo or UTC).timestamp()),
            players=p.player_count,
            queue=p.queue_count,
            spectators=p.spectator_count,
            max_players=p.max_player_count,
        )
        for p in rows
    ]
