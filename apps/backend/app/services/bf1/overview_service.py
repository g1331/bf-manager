"""BF1 全服统计聚合服务

后台定时任务拉取全量服务器列表聚合为全服快照写入 Redis，前端只读缓存，避免每个访客触发
一次全量拉取。数据源优先用一次 Blaze ``GameManager.getGameListSnapshot``（复用玩家列表的
Blaze 长连接）；快照失败时回退为并发调用 Gateway ``GameServer.searchServers`` 并按 guid 去重。

聚合口径与上游 bf1 信息查询保持一致：官方服按 is_official 判定，地区按 EA 区域代号
归入亚洲（Asia）、欧洲（EU）与其他三档。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.domain.games.bf1.maps import (
    MapData,
    normalize_map_image_url,
    translate_map_name,
    translate_mode_name,
    translate_region,
)
from app.schemas.bf1.overview import BF1Overview, CountBreakdown, NamedCount, TrendPoint
from app.schemas.bf1.server import ServerSummary
from app.services.bf1.blaze_service import fetch_game_list_snapshot
from app.services.bf1.gateway_factory import get_bf1_client
from app.services.bf1.server_player_count_service import record_player_counts
from app.services.bf1.server_service import _to_summary
from app.services.bf1.server_snapshot_cache import write_server_snapshot

# searchServers 单次最多约 200 条，并发多次再按 guid 去重以逼近全量。
SEARCH_CONCURRENCY = 50
SEARCH_LIMIT = 200
# 热门地图模式展示条数
TOP_MAP_MODE_LIMIT = 8
# 概览页「最热闹的服务器」条数
TOP_SERVER_LIMIT = 10

# 全服统计专用筛选条件：只按服务器类型与人数档位过滤，与上游 bf1 信息查询完全一致。
# 网关默认 filter_dict 额外带 maps / gameModes 等维度的白名单，会改变 EA 返回的服务器
# 集合，使总数偏离游戏内实际口径，故全服统计改走这份精简条件。
OVERVIEW_FILTER = {
    "name": "",
    "serverType": {
        "OFFICIAL": "on",
        "RANKED": "on",
        "UNRANKED": "on",
        "PRIVATE": "on",
    },
    "slots": {
        "oneToFive": "on",
        "sixToTen": "on",
        "none": "on",
        "tenPlus": "on",
        "spectator": "on",
    },
}

# 缓存键与过期时间：TTL 远大于轮询周期，容忍连续数次拉取失败而不丢失上一次快照。
OVERVIEW_CACHE_KEY = "bf1:overview"
OVERVIEW_CACHE_TTL = 600
POLL_INTERVAL_SECONDS = 60

# 24h 趋势历史：poller 每轮成功刷新追加一个点，按轮询周期保留约 24 小时。
# TTL 给两天，服务长期停摆后陈旧曲线自动过期，而短暂重启不丢历史。
HISTORY_CACHE_KEY = "bf1:overview:history"
HISTORY_MAX_POINTS = 24 * 60 * 60 // POLL_INTERVAL_SECONDS
HISTORY_CACHE_TTL = 2 * 24 * 60 * 60


def _region_key(region_code: str | None) -> str:
    if region_code == "Asia":
        return "asia"
    if region_code == "EU":
        return "eu"
    return "other"


def _accumulate(bucket: CountBreakdown, value: int, *, is_official: bool, region_key: str) -> None:
    bucket.total += value
    if is_official:
        bucket.official += value
    else:
        bucket.private += value
    setattr(bucket, region_key, getattr(bucket, region_key) + value)


def build_overview(
    summaries: list[ServerSummary],
    *,
    sample_pulls: int,
    raw_count: int,
) -> BF1Overview:
    """把去重后的服务器摘要列表聚合成全服快照。纯函数，便于单测。"""
    servers = CountBreakdown()
    players = CountBreakdown()
    queues = CountBreakdown()
    spectators = CountBreakdown()

    map_mode_servers: dict[str, int] = defaultdict(int)
    map_mode_players: dict[str, int] = defaultdict(int)
    map_mode_image: dict[str, str] = {}
    mode_servers: dict[str, int] = defaultdict(int)
    mode_players: dict[str, int] = defaultdict(int)

    for s in summaries:
        region_key = _region_key(s.region)
        is_official = s.is_official

        _accumulate(servers, 1, is_official=is_official, region_key=region_key)
        _accumulate(players, s.player_count, is_official=is_official, region_key=region_key)
        _accumulate(queues, s.queue_count, is_official=is_official, region_key=region_key)
        _accumulate(spectators, s.spectator_count, is_official=is_official, region_key=region_key)

        mode_label = s.mode_display_name or s.game_mode or "未知模式"
        map_label = s.map_display_name or s.map_name or "未知地图"
        map_mode_label = f"{mode_label} · {map_label}"

        map_mode_servers[map_mode_label] += 1
        map_mode_players[map_mode_label] += s.player_count
        if s.map_image_url and map_mode_label not in map_mode_image:
            map_mode_image[map_mode_label] = s.map_image_url
        mode_servers[mode_label] += 1
        mode_players[mode_label] += s.player_count

    top_map_modes = sorted(
        (
            NamedCount(
                label=label,
                servers=cnt,
                players=map_mode_players[label],
                image=map_mode_image.get(label),
            )
            for label, cnt in map_mode_servers.items()
        ),
        key=lambda x: (x.players, x.servers),
        reverse=True,
    )[:TOP_MAP_MODE_LIMIT]

    mode_distribution = sorted(
        (
            NamedCount(label=label, servers=cnt, players=mode_players[label])
            for label, cnt in mode_servers.items()
        ),
        key=lambda x: (x.servers, x.players),
        reverse=True,
    )

    return BF1Overview(
        available=True,
        updated_at=datetime.now(UTC).isoformat(),
        sample_pulls=sample_pulls,
        raw_count=raw_count,
        servers=servers,
        players=players,
        queues=queues,
        spectators=spectators,
        top_map_modes=top_map_modes,
        mode_distribution=mode_distribution,
        top_servers=sorted(summaries, key=lambda s: (s.player_count, s.queue_count), reverse=True)[
            :TOP_SERVER_LIMIT
        ],
    )


def _snapshot_mode(attrs: dict[str, Any]) -> str | None:
    """从 Blaze ATTR 找出与 Gateway mapMode 同口径的模式代号（ModeDict 的键）。

    shortcut: 模式字段名未实测，按名字含 mode 或 levellocation 的键逐个尝试，值依次试原值、
    去尾部数字、再去 Large 后缀，命中 ModeDict 即采用；字段名实测确认后可收窄为单键。
    """
    for key, value in attrs.items():
        lowered = key.lower()
        if not isinstance(value, str) or ("mode" not in lowered and lowered != "levellocation"):
            continue
        candidate = value.rsplit("_", 1)[-1].rstrip("0123456789")
        for code in (value, candidate, candidate.removesuffix("Large")):
            if code in MapData.ModeDict:
                return code
    return None


def _snapshot_summary(game: dict[str, Any]) -> ServerSummary:
    """把快照里的一个游戏转成 ServerSummary，字段足够聚合与服务器列表展示。"""
    attrs = game.get("ATTR") or {}
    mode = _snapshot_mode(attrs)
    if mode is None:
        # 只带键名与模式相关的值，ATTR 其它值（管理名单等）不进日志
        hints = {k: v for k, v in attrs.items() if "mode" in k.lower() or "level" in k.lower()}
        raise ValueError(f"快照 ATTR 中找不到可识别的模式: keys={sorted(attrs)} hints={hints}")
    level = attrs.get("level") or None
    # PCNT = [公开玩家, 私有玩家, 公开观战, 私有观战]
    pcnt = [*(game.get("PCNT") or []), 0, 0, 0, 0]
    # CAP 与 PCNT 同序，首项是公开玩家位即服务器规模
    cap = [*(game.get("CAP") or []), 0]
    # 描述与 admins 一样按长度切片存放，按序拼接
    description = "".join(attrs.get(f"description{i}") or "" for i in range(1, 10))
    region = attrs.get("region")
    server_type = attrs.get("servertype")
    return ServerSummary(
        server_id=0,
        game_id=game.get("GID"),
        name=game.get("GNAM") or "",
        map_name=level,
        map_display_name=translate_map_name(level),
        map_image_url=normalize_map_image_url(MapData.MapImageDict.get(level or "")),
        game_mode=mode,
        mode_display_name=translate_mode_name(mode),
        player_count=pcnt[0] + pcnt[1],
        max_player_count=int(cap[0] or 0),
        queue_count=int(game.get("QCNT") or 0),
        spectator_count=pcnt[2] + pcnt[3],
        region=region,
        region_display_name=translate_region(region),
        # shortcut: PSAS 是 Blaze 标准的 pingSiteAlias，未在生产快照里实测；国家、tickRate、
        # 密码字段名未知暂缺，列表页对应的国旗回落 ping 节点、锁与 Hz 不显示，实测后补上。
        ping_site=game.get("PSAS") or None,
        is_official=server_type == "OFFICIAL",
        is_ranked=server_type == "RANKED",
        description=description or None,
    )


def snapshot_summaries(updates: list[dict[str, Any]]) -> list[ServerSummary]:
    """把 NotifyGameListUpdate 的 UPDT 项按 GID 去重后逐个转成 ServerSummary。纯函数，便于单测。

    任一服务器解析不出模式即抛出，宁可回退 searchServers，也不让标签与现有口径不一致。
    """
    games: dict[int, dict[str, Any]] = {}
    for update in updates:
        game = update.get("GAM") or update
        if game.get("GID") is not None:
            games[game["GID"]] = game
    if not games:
        raise ValueError("快照没有返回任何服务器")
    return [_snapshot_summary(game) for game in games.values()]


def build_overview_from_snapshot(updates: list[dict[str, Any]]) -> BF1Overview:
    """把快照 UPDT 项聚合成全服统计。纯函数，便于单测。"""
    return build_overview(snapshot_summaries(updates), sample_pulls=1, raw_count=len(updates))


async def fetch_overview(db: AsyncSession) -> tuple[BF1Overview, list[ServerSummary], str]:
    """拉取并聚合全服统计：先试 Blaze 快照，失败（含超时）打 warning 后回退 searchServers。

    返回 (统计, 去重后的服务器摘要, 数据源 snapshot/search)。无任何数据时抛出，由调用方
    决定是否覆盖缓存。
    """
    if not get_settings().blaze_mock_mode:
        try:
            updates = await fetch_game_list_snapshot(db)
            summaries = snapshot_summaries(updates)
        except Exception as e:
            logger.warning("BF1 overview snapshot failed, falling back to searchServers: {}", e)
        else:
            logger.info("BF1 overview source=snapshot games={}", len(summaries))
            overview = build_overview(summaries, sample_pulls=1, raw_count=len(updates))
            return overview, summaries, "snapshot"
    overview, summaries = await _fetch_overview_by_search(db)
    return overview, summaries, "search"


async def _fetch_overview_by_search(db: AsyncSession) -> tuple[BF1Overview, list[ServerSummary]]:
    """并发 searchServers 拉取并聚合全服统计。无任何一次成功拉取时抛出。

    去重、判空与抛出全部放在 ``get_bf1_client`` 上下文内：searchServers 失败只返回字符串
    而非抛异常，若全失败时让上下文正常退出，工厂会走成功分支 mark_used 并清零失败计数，
    导致失效账号每轮被"治愈"、永不被 mark_failure 自动淘汰。把全失败的抛出留在上下文内，
    异常即由工厂的 except 分支记为 mark_failure，与 server_service 等既有服务范式一致。
    """
    async with get_bf1_client(db) as client:
        tasks = [
            client.searchServers("", limit=SEARCH_LIMIT, filter_dict=OVERVIEW_FILTER)
            for _ in range(SEARCH_CONCURRENCY)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        deduped: dict[str, dict] = {}
        sample_pulls = 0
        raw_count = 0
        for res in results:
            if isinstance(res, BaseException) or not isinstance(res, dict):
                continue
            gameservers = (res.get("result") or {}).get("gameservers") or []
            sample_pulls += 1
            for raw in gameservers:
                raw_count += 1
                guid = raw.get("guid")
                if not guid or guid in deduped:
                    continue
                deduped[guid] = raw

        if sample_pulls == 0:
            raise RuntimeError("searchServers 全部失败，未取得任何服务器数据")

        summaries = [_to_summary(raw) for raw in deduped.values()]
        logger.info("BF1 overview source=search pulls={}/{}", sample_pulls, SEARCH_CONCURRENCY)
        overview = build_overview(summaries, sample_pulls=sample_pulls, raw_count=raw_count)
        return overview, summaries


async def refresh_overview_cache(db: AsyncSession) -> BF1Overview:
    """拉取并写入缓存。拉取失败时抛出，保留上一次快照不被覆盖。

    快照与趋势历史分开存储：快照整体覆盖写，历史按采样点追加并裁剪到最近 24h，
    读取端再把两者拼装成完整响应。
    """
    overview, summaries, source = await fetch_overview(db)
    cache = await get_cache()
    await cache.set(OVERVIEW_CACHE_KEY, overview.model_dump(), ttl=OVERVIEW_CACHE_TTL)
    await write_server_snapshot(summaries, source=source, ttl=OVERVIEW_CACHE_TTL)
    _spawn_record_player_counts(summaries)
    point = TrendPoint(
        ts=int(datetime.now(UTC).timestamp()),
        players=overview.players.total,
        servers=overview.servers.total,
    )
    await cache.list_append(
        HISTORY_CACHE_KEY,
        point.model_dump(),
        max_len=HISTORY_MAX_POINTS,
        ttl=HISTORY_CACHE_TTL,
    )
    logger.info(
        "BF1 overview refreshed: servers={} players={} pulls={} raw={}",
        overview.servers.total,
        overview.players.total,
        overview.sample_pulls,
        overview.raw_count,
    )
    return overview


# 后台写点任务的强引用，防止任务未完成就被 GC 回收
_background_tasks: set[asyncio.Task[None]] = set()


async def _record_player_counts(summaries: list[ServerSummary]) -> None:
    try:
        async with get_sessionmaker()() as db:
            written = await record_player_counts(db, summaries)
        logger.debug("BF1 server player counts recorded: {}", written)
    except Exception as e:
        logger.warning("BF1 server player count write failed: {}", e)


def _spawn_record_player_counts(summaries: list[ServerSummary]) -> None:
    """人数点写库放到独立任务和会话里，不阻塞、不拖慢快照轮询。"""
    task = asyncio.create_task(_record_player_counts(summaries))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def read_overview_cache() -> BF1Overview:
    """只读缓存。无缓存或缓存层不可用时返回 available=False 的空快照。

    该端点公开访问，Redis 在本项目属可选依赖，连接异常时降级返回空快照而非报错。
    """
    try:
        cache = await get_cache()
        cached = await cache.get(OVERVIEW_CACHE_KEY)
    except RedisError as e:
        logger.warning("BF1 overview cache read failed, serving empty snapshot: {}", e)
        return BF1Overview(available=False)
    if not cached:
        return BF1Overview(available=False)
    overview = BF1Overview(**cached)
    try:
        overview.history = [TrendPoint(**p) for p in await cache.list_all(HISTORY_CACHE_KEY)]
    except (RedisError, ValueError) as e:
        logger.warning("BF1 overview history read failed, serving snapshot without trend: {}", e)
    return overview


async def overview_poller() -> None:
    """后台定时轮询循环。在应用 lifespan 中以 asyncio 任务启动。"""
    while True:
        try:
            async with get_sessionmaker()() as db:
                await refresh_overview_cache(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("BF1 overview poll failed: {}", e)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
