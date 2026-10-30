"""BF1 私服名单与天眼查

getFullServerDetails 的 rspInfo 里带着服主、管理、VIP、封禁四份名单。快照解析 serverId 时本来
就要拉一次，这里把名单顺手存下；之后每轮从快照里挑名单最旧的几台服重新拉，每台约
REFRESH_INTERVAL 刷新一次。服务器详情页拉到的名单也会写回来（同一台服 DETAIL_MIN_AGE 内只写一次）。

存下来的名单按 personaId 反查，就是旧机器人的「天眼查」：某人是哪些服的服主 / 管理 / VIP、
被哪些服封禁。只覆盖快照里出现过的有服主的服，从没有人进过的空服查不到。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.models.bf1.rsp_lists import Bf1RspMember, Bf1RspServer
from app.schemas.bf1.server import (
    PlayerRspServer,
    PlayerRspServers,
    ServerExtras,
    ServerSummary,
)
from app.services.bf1.server_roster_service import insert_for
from app.services.bf1.server_service import BF1ServerService
from app.services.bf1.server_snapshot_cache import read_server_snapshot

ROLES = ("owner", "admin", "vip", "ban")
# 150 多台私服每台 6 小时刷新一次，平均每分钟不到一次请求
REFRESH_INTERVAL = timedelta(hours=6)
# 首次上线时名单全空，按每轮 3 台约 50 分钟补齐
REFRESH_PER_ROUND = 3
# 详情页每次打开都会拉到名单，同一台服短时间内不重复写
DETAIL_MIN_AGE = timedelta(minutes=10)
# 这么久没刷新到的服（一直没人或已到期关服）连名单一起清掉
STALE_AFTER = timedelta(days=30)


def _aware(ts: datetime) -> datetime:
    # sqlite 读回的是无时区时间，按写入时的 UTC 补上
    return ts.replace(tzinfo=ts.tzinfo or UTC)


def _member_rows(server_id: int, extras: ServerExtras) -> list[dict]:
    rows: dict[tuple[str, int], dict] = {}
    groups = {
        "owner": [extras.owner] if extras.owner and extras.owner.persona_id else [],
        "admin": extras.admins,
        "vip": extras.vips,
        "ban": extras.banned,
    }
    for role, members in groups.items():
        for m in members:
            pid = int(m.persona_id or 0)
            if pid:
                name = (m.display_name or "")[:64] or None
                rows[(role, pid)] = {"server_id": server_id, "role": role, "pid": pid, "name": name}
    return list(rows.values())


async def store_lists(
    db: AsyncSession,
    server_id: int,
    game_id: int,
    name: str,
    extras: ServerExtras,
    now: datetime | None = None,
) -> None:
    """整服替换一台服的名单，不提交。"""
    now = now or datetime.now(UTC)
    stmt = insert_for(db, Bf1RspServer).values(
        server_id=server_id, game_id=game_id, name=name[:255], refreshed_at=now
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["server_id"],
            set_={
                "game_id": stmt.excluded.game_id,
                "name": stmt.excluded.name,
                "refreshed_at": stmt.excluded.refreshed_at,
            },
        )
    )
    await db.execute(delete(Bf1RspMember).where(Bf1RspMember.server_id == server_id))
    rows = _member_rows(server_id, extras)
    if rows:
        await db.execute(insert_for(db, Bf1RspMember).values(rows))


async def remember_detail_lists(
    db: AsyncSession, game_id: int, name: str, extras: ServerExtras
) -> None:
    """详情页拉到的名单写回来；失败只记日志，不影响详情页。"""
    if not extras.server_id or not extras.owner:
        return
    try:
        last = await db.scalar(
            select(Bf1RspServer.refreshed_at).where(Bf1RspServer.server_id == extras.server_id)
        )
        now = datetime.now(UTC)
        if last is not None and now - _aware(last) < DETAIL_MIN_AGE:
            return
        await store_lists(db, extras.server_id, game_id, name, extras, now)
        await db.commit()
    except Exception as e:
        logger.warning("BF1 rsp lists write from detail failed: {}", e)
        await db.rollback()


async def refresh_stale_lists(
    db: AsyncSession, summaries: list[ServerSummary], server_ids: dict[int, int]
) -> int:
    """从本轮快照里挑名单缺失或最旧的服重新拉，每轮最多 REFRESH_PER_ROUND 台；顺带清理过期服。

    server_ids 是 resolve_server_ids 给出的 gameId → serverId。返回本轮刷新的台数。
    """
    now = datetime.now(UTC)
    current: dict[int, tuple[int, str]] = {}
    for s in summaries:
        gid = int(s.game_id or 0)
        sid = server_ids.get(gid)
        if sid and s.name:
            current[sid] = (gid, s.name)
    refreshed = (
        {
            sid: _aware(ts)
            for sid, ts in (
                await db.execute(
                    select(Bf1RspServer.server_id, Bf1RspServer.refreshed_at).where(
                        Bf1RspServer.server_id.in_(list(current))
                    )
                )
            ).all()
        }
        if current
        else {}
    )
    epoch = datetime.min.replace(tzinfo=UTC)
    due = sorted(
        (sid for sid in current if now - refreshed.get(sid, epoch) >= REFRESH_INTERVAL),
        key=lambda sid: refreshed.get(sid, epoch),
    )

    done = 0
    service = BF1ServerService(db)
    for sid in due[:REFRESH_PER_ROUND]:
        gid, name = current[sid]
        try:
            got = await service.get_extras(gid)
        except EAApiError as e:
            logger.warning("BF1 rsp lists refresh failed, retry next round: {}", e)
            break
        if got is None or got[0].server_id != sid:
            continue
        await store_lists(db, sid, gid, got[1] or name, got[0], now)
        done += 1

    stale = select(Bf1RspServer.server_id).where(Bf1RspServer.refreshed_at < now - STALE_AFTER)
    # sqlite 测试库不开外键，成员行显式删
    await db.execute(delete(Bf1RspMember).where(Bf1RspMember.server_id.in_(stale)))
    await db.execute(delete(Bf1RspServer).where(Bf1RspServer.refreshed_at < now - STALE_AFTER))
    await db.commit()
    return done


async def list_player_servers(db: AsyncSession, persona_id: int) -> PlayerRspServers:
    """天眼查：按角色列出这个人在收录私服里的身份，每类按服名排序。"""
    rows = (
        await db.execute(
            select(Bf1RspMember.role, Bf1RspServer)
            .join(Bf1RspServer, Bf1RspServer.server_id == Bf1RspMember.server_id)
            .where(Bf1RspMember.pid == persona_id)
            .order_by(Bf1RspServer.name)
        )
    ).all()
    tracked = await db.scalar(select(func.count()).select_from(Bf1RspServer)) or 0
    live = {int(s.game_id or 0): s for s in (await read_server_snapshot() or [])}

    out = PlayerRspServers(tracked_servers=tracked)
    for role, srv in rows:
        if role not in ROLES:
            continue
        s = live.get(srv.game_id)
        getattr(out, role).append(
            PlayerRspServer(
                server_id=srv.server_id,
                game_id=srv.game_id,
                name=srv.name,
                refreshed_at=int(_aware(srv.refreshed_at).timestamp()),
                player_count=s.player_count if s else None,
                max_player_count=s.max_player_count if s else None,
                map_display_name=s.map_display_name if s else None,
                map_image_url=s.map_image_url if s else None,
            )
        )
    return out
