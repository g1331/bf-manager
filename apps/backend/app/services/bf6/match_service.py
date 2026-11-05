"""BF6 对局估算：存快照、做差、后台复查。

- 战绩页每次真正向 EA 拉生涯时调 ``record``：第一次见到这名玩家就存一份快照开始记录，
  之后每次和上一份做差，场次或战斗时间涨了就写一条估算。
- 后台 ``tracker_poller`` 每分钟挑一批到期的玩家一起重读生涯（一次请求最多 ``BATCH`` 人）：
  最近 ``TRACK_WINDOW`` 内有人看过的才复查；两小时内有变化的按 ``FAST_INTERVAL``，否则按 ``SLOW_INTERVAL``。
  到期的人多于一批时按上次复查时间排队，请求量不会超过每分钟一批。
- 复查读到的生涯同时写进战绩缓存，页面打开时就是最新的。
"""

from __future__ import annotations

import asyncio
import json
import zlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import and_, delete, or_, select, update

from app.domain.games.bf6 import client as bf6
from app.models.bf6_match import Bf6MatchEstimate, Bf6StatSnapshot
from app.schemas.bf6.matches import Bf6MatchDelta, Bf6MatchList
from app.schemas.bf6.matches import Bf6MatchEstimate as Bf6MatchEstimateOut
from app.services.account_service import SessionFactory
from app.services.bf1.server_roster_service import insert_for
from app.services.bf6.match_delta import diff, regressed

TRACK_WINDOW = timedelta(days=7)
FAST_INTERVAL = timedelta(minutes=10)
SLOW_INTERVAL = timedelta(minutes=30)
ACTIVE_WINDOW = timedelta(hours=2)
BATCH = 16
TICK_SECONDS = 60
# 凭据不可用（没填、被拒）时不必每分钟都试
_UNAVAILABLE_BACKOFF_SECONDS = 600
ESTIMATE_RETENTION = timedelta(days=90)
# 停止复查后快照再留一段时间，期间有人再看还能接着算
SNAPSHOT_RETENTION = timedelta(days=30)
LIST_LIMIT = 30
# 累计值回退持续这么久才当作统计被重置
REBASE_AFTER = timedelta(days=1)


def _pack(stats: dict[str, int]) -> bytes:
    return zlib.compress(json.dumps(stats, separators=(",", ":")).encode())


def _unpack(blob: bytes) -> dict[str, int]:
    data = json.loads(zlib.decompress(blob))
    return {str(k): int(v) for k, v in data.items()}


def _aware(at: datetime) -> datetime:
    # sqlite 读回来不带时区
    return at if at.tzinfo else at.replace(tzinfo=UTC)


async def record(
    session_factory: SessionFactory,
    nucleus_id: int,
    stats: dict[str, int],
    now: datetime,
    *,
    viewed: bool,
) -> Bf6MatchDelta | None:
    """存下这次读到的生涯，返回新写入的估算。stats 为空（EA 没返回、玩家没打过）时什么都不做。

    now 是拿到这份响应的时刻。viewed 为真表示有人打开了战绩页：没记录过的玩家从这时开始记录，
    记录中的刷新最近查看时间。后台复查传 False，不会让没人看的玩家一直被复查下去。

    基线（stats + polled_at）只往前走：比基线还早拿到的响应直接丢掉；累计值比基线小（EA 暂时回了旧值，
    或页面与后台的响应先后颠倒）时保留基线，免得恢复后把同一局再记一遍。回退持续超过
    ``REBASE_AFTER`` 才当作统计被重置，换成新基线。
    """
    if not stats:
        return None
    async with session_factory() as db:
        row = await db.scalar(
            select(Bf6StatSnapshot)
            .where(Bf6StatSnapshot.nucleus_id == nucleus_id)
            .with_for_update()
        )
        if row is None:
            if not viewed:
                return None
            stmt = insert_for(db, Bf6StatSnapshot).values(
                nucleus_id=nucleus_id,
                stats=_pack(stats),
                created_at=now,
                polled_at=now,
                checked_at=now,
                changed_at=now,
                viewed_at=now,
            )
            # 页面和后台同时第一次读到时，先写的那份为准
            await db.execute(stmt.on_conflict_do_nothing(index_elements=["nucleus_id"]))
            await db.commit()
            return None

        if viewed:
            row.viewed_at = max(_aware(row.viewed_at), now)
        row.checked_at = max(_aware(row.checked_at), now)
        baseline_at = _aware(row.polled_at)
        delta: Bf6MatchDelta | None = None
        prev = _unpack(row.stats)
        if now <= baseline_at:
            # 比基线还早拿到的响应：数据不会比基线新，只算复查过
            pass
        elif regressed(prev, stats):
            if now - baseline_at >= REBASE_AFTER:
                logger.warning("BF6 生涯累计值回退超过一天，重新建基线 nucleus={}", nucleus_id)
                row.stats = _pack(stats)
                row.polled_at = row.changed_at = now
        else:
            delta = diff(prev, stats)
            if delta is not None:
                db.add(
                    Bf6MatchEstimate(
                        nucleus_id=nucleus_id,
                        started_after=baseline_at,
                        observed_at=now,
                        matches=delta.matches,
                        payload=delta.model_dump(mode="json"),
                    )
                )
            if stats != prev:
                row.stats = _pack(stats)
                row.changed_at = now
            row.polled_at = now
        await db.commit()
        return delta


async def touch(session_factory: SessionFactory, nucleus_id: int, now: datetime) -> None:
    """战绩走缓存时也算有人看过，记录中的玩家继续复查。"""
    async with session_factory() as db:
        row = await db.get(Bf6StatSnapshot, nucleus_id)
        # 一小时内看过的不再写库
        if row is not None and _aware(row.viewed_at) < now - timedelta(hours=1):
            row.viewed_at = now
            await db.commit()


async def list_estimates(session_factory: SessionFactory, nucleus_id: int) -> Bf6MatchList:
    async with session_factory() as db:
        snapshot = await db.get(Bf6StatSnapshot, nucleus_id)
        rows = (
            await db.scalars(
                select(Bf6MatchEstimate)
                .where(Bf6MatchEstimate.nucleus_id == nucleus_id)
                .order_by(Bf6MatchEstimate.observed_at.desc(), Bf6MatchEstimate.id.desc())
                .limit(LIST_LIMIT)
            )
        ).all()
    now = datetime.now(UTC)
    tracking = snapshot is not None and _aware(snapshot.viewed_at) >= now - TRACK_WINDOW
    return Bf6MatchList(
        tracking=tracking,
        tracked_since=_aware(snapshot.created_at) if snapshot else None,
        last_checked_at=_aware(snapshot.polled_at) if snapshot else None,
        matches=[
            Bf6MatchEstimateOut(
                **row.payload,
                id=row.id,
                started_after=_aware(row.started_after),
                observed_at=_aware(row.observed_at),
            )
            for row in rows
        ],
    )


async def due_players(session_factory: SessionFactory, now: datetime) -> list[int]:
    async with session_factory() as db:
        rows = await db.scalars(
            select(Bf6StatSnapshot.nucleus_id)
            .where(
                Bf6StatSnapshot.viewed_at >= now - TRACK_WINDOW,
                or_(
                    Bf6StatSnapshot.checked_at <= now - SLOW_INTERVAL,
                    and_(
                        Bf6StatSnapshot.changed_at >= now - ACTIVE_WINDOW,
                        Bf6StatSnapshot.checked_at <= now - FAST_INTERVAL,
                    ),
                ),
            )
            .order_by(Bf6StatSnapshot.checked_at)
            .limit(BATCH)
        )
        return list(rows.all())


async def purge_expired(session_factory: SessionFactory, now: datetime) -> None:
    async with session_factory() as db:
        await db.execute(
            delete(Bf6MatchEstimate).where(Bf6MatchEstimate.observed_at < now - ESTIMATE_RETENTION)
        )
        await db.execute(
            delete(Bf6StatSnapshot).where(
                Bf6StatSnapshot.viewed_at < now - TRACK_WINDOW - SNAPSHOT_RETENTION
            )
        )
        await db.commit()


# 批量读生涯并处理结果，由 player_service 提供（它管凭据、会话续期和战绩缓存）
FetchBatch = Callable[[list[int]], Awaitable[dict[int, dict[str, int]]]]


async def poll_once(
    session_factory: SessionFactory,
    fetch: FetchBatch,
    now: datetime,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """复查一批到期的玩家，返回这批人数。EA 没返回的人（关了数据分享等）保留原快照。

    now 用来挑到期的人；记录用 clock() 取拿到响应的时刻，估算的时间区间才不会早于实际读到的时间。
    """
    due = await due_players(session_factory, now)
    if not due:
        return 0
    fetched = await fetch(due)
    observed = max(clock(), now)
    missing = [nid for nid in due if not fetched.get(nid)]
    for nucleus_id in due:
        stats = fetched.get(nucleus_id)
        if stats:
            await record(session_factory, nucleus_id, stats, observed, viewed=False)
    if missing:
        # 只记成复查过，免得这些人一直排在队首；基线和它的时间不动
        async with session_factory() as db:
            await db.execute(
                update(Bf6StatSnapshot)
                .where(
                    Bf6StatSnapshot.nucleus_id.in_(missing),
                    Bf6StatSnapshot.checked_at < observed,
                )
                .values(checked_at=observed)
            )
            await db.commit()
    return len(due)


async def tracker_poller(session_factory: SessionFactory, fetch: FetchBatch) -> None:
    last_purge: datetime | None = None
    while True:
        delay = TICK_SECONDS
        now = datetime.now(UTC)
        try:
            if last_purge is None or now - last_purge >= timedelta(hours=1):
                await purge_expired(session_factory, now)
                last_purge = now
            await poll_once(session_factory, fetch, now)
        except asyncio.CancelledError:
            raise
        except bf6.Bf6Error as e:
            # 凭据问题已经记在凭据状态里，这里只放慢节奏
            logger.warning("BF6 对局复查失败: {}", e)
            if not e.retryable:
                delay = _UNAVAILABLE_BACKOFF_SECONDS
        except Exception as e:
            # 后台循环不能因为一次意外就停掉
            logger.exception("BF6 对局复查出错: {!r}", e)
        await asyncio.sleep(delay)
