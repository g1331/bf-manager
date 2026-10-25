"""BF1 站内登记服务器的人数时序

全服统计每轮拿到全服摘要后，为 ``servers`` 表里已登记、且本轮出现在摘要中的服务器各写
一个人数点，并清理超过保留期的旧点；服务器详情页据此画 24 小时人数曲线。
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bf1.server_player_count import Bf1ServerPlayerCount
from app.models.server import Server
from app.schemas.bf1.server import ServerPlayerCountPoint, ServerSummary

RETENTION = timedelta(days=7)


async def record_player_counts(db: AsyncSession, summaries: list[ServerSummary]) -> int:
    """写入本轮人数点并清理过期点，返回写入条数。

    先按 servers.game_id 匹配；对不上时按服名回退（服务器重启会换 gameId，而 game_id 只在
    鉴权识别时回填），命中后把新 gameId 写回登记表。本轮同名的多个服不参与名称匹配。
    shortcut: 服主改名后名称回退失效，要等鉴权识别更新名称；快照若能拿到 serverId /
    persistedGameId 再改用稳定键。
    """
    now = datetime.now(UTC)
    by_gid = {s.game_id: s for s in summaries if s.game_id}
    name_counts = Counter(s.name for s in summaries if s.name)
    by_name = {s.name: s for s in summaries if s.name and name_counts[s.name] == 1}
    written = 0
    for server in await db.scalars(select(Server).where(Server.game == "bf1")):
        s = by_gid.get(server.game_id) if server.game_id else None
        if s is None and server.name:
            s = by_name.get(server.name)
            if s is not None:
                server.game_id = s.game_id
        if s is None:
            continue
        db.add(
            Bf1ServerPlayerCount(
                server_pk=server.id,
                player_count=s.player_count,
                queue_count=s.queue_count,
                spectator_count=s.spectator_count,
                max_player_count=s.max_player_count,
                sampled_at=now,
            )
        )
        written += 1
    await db.execute(
        delete(Bf1ServerPlayerCount).where(Bf1ServerPlayerCount.sampled_at < now - RETENTION)
    )
    await db.commit()
    return written


async def list_player_counts(
    db: AsyncSession, game_id: int, *, hours: int = 24
) -> list[ServerPlayerCountPoint]:
    """某服务器最近 hours 小时的人数点，按时间升序。未登记的服务器返回空列表。"""
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = await db.scalars(
        select(Bf1ServerPlayerCount)
        .join(Server, Server.id == Bf1ServerPlayerCount.server_pk)
        .where(
            Server.game == "bf1",
            Server.game_id == game_id,
            Bf1ServerPlayerCount.sampled_at >= since,
        )
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
