"""BF1 服务器查询路由"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.schemas.bf1.rounds import RoundPage
from app.schemas.bf1.server import (
    ServerDetail,
    ServerLeaderboard,
    ServerListResponse,
    ServerMapStat,
    ServerPlayerCountPoint,
    ServerPlayersResponse,
    ServerRosterPage,
    ServerRosterSnapshot,
)
from app.services.bf1.blaze_service import get_server_players
from app.services.bf1.round_service import list_server_rounds
from app.services.bf1.server_player_count_service import (
    get_leaderboard,
    get_roster_snapshot,
    list_map_stats,
    list_player_counts,
    list_roster_points,
)
from app.services.bf1.server_service import BF1ServerService

router = APIRouter()


@router.get("", response_model=ServerListResponse)
async def list_servers(
    db: DbDep,
    name: str | None = Query(
        None, max_length=64, description="按服务器名关键字过滤（EA 端包含匹配，大小写不敏感）"
    ),
    maps: list[str] | None = Query(None, description="地图代号（MP_*），多值取并集"),
    modes: list[str] | None = Query(None, description="模式代号，多值取并集"),
    regions: list[str] | None = Query(None, description="地区代号，多值取并集"),
    sizes: list[int] | None = Query(None, description="服务器最大人数档位，多值取并集"),
    limit: int = Query(200, ge=1, le=500),
    include_empty: bool = Query(
        False, description="包含 0 人的空服；全服快照不含空服，开启后改走 EA searchServers"
    ),
) -> ServerListResponse:
    # 默认在全服快照缓存上本地筛选，缓存缺失或要空服时下推 EA searchServers。空位
    # （emptySlots）由前端二次过滤。接口没有 offset，前端走客户端分批渲染。
    return await BF1ServerService(db).search(
        keyword=name,
        maps=maps,
        modes=modes,
        regions=regions,
        sizes=sizes,
        limit=limit,
        include_empty=include_empty,
    )


@router.get("/{game_id}", response_model=ServerDetail)
async def get_server(game_id: int, db: DbDep) -> ServerDetail:
    return await BF1ServerService(db).get_detail(game_id)


@router.get("/{game_id}/players", response_model=ServerPlayersResponse)
async def get_server_players_route(
    game_id: int,
    db: DbDep,
    include_stats: bool = Query(
        True, description="是否合并各玩家生涯综合战绩（胜率 / KD / KPM / 时长），关闭可加快响应"
    ),
) -> ServerPlayersResponse:
    # 玩家列表走 Blaze 长连接拉取实时房间名单，叠加 RSP 管理 / VIP 名单与平台绑定标记。
    # 战绩为可选的慢路径，按 include_stats 控制是否并发查询。
    return await get_server_players(db, game_id, include_stats=include_stats)


@router.get("/{game_id}/player-counts", response_model=list[ServerPlayerCountPoint])
async def get_server_player_counts(game_id: int, db: DbDep) -> list[ServerPlayerCountPoint]:
    # 人数点由全服统计轮询每分钟写入一次，服重启前后的实例合在一起
    return await list_player_counts(db, game_id)


@router.get("/{game_id}/map-stats", response_model=list[ServerMapStat])
async def get_server_map_stats(
    game_id: int, db: DbDep, days: int = Query(7, ge=1, le=7)
) -> list[ServerMapStat]:
    # 由人数采样里的地图字段聚合，采样保留 7 天，days 最多 7
    return await list_map_stats(db, game_id, days=days)


@router.get("/{game_id}/leaderboard", response_model=ServerLeaderboard)
async def get_server_leaderboard(
    game_id: int,
    db: DbDep,
    days: int = Query(7, ge=1, le=7),
    limit: int = Query(50, ge=1, le=100),
) -> ServerLeaderboard:
    # 由快照名单的进出事件算在队时长，名单保留 7 天，days 最多 7
    return await get_leaderboard(db, game_id, days=days, limit=limit)


@router.get("/{game_id}/snapshots", response_model=ServerRosterPage)
async def get_server_snapshots(
    game_id: int,
    db: DbDep,
    before: int | None = Query(
        None, description="只取这个 unix 秒之前的快照，传上一页的 next_before"
    ),
    limit: int = Query(50, ge=1, le=200),
) -> ServerRosterPage:
    # 名单随全服统计每分钟记录一次，保留 7 天
    return await list_roster_points(db, game_id, before=before, limit=limit)


@router.get("/{game_id}/snapshots/{ts}", response_model=ServerRosterSnapshot)
async def get_server_snapshot(game_id: int, ts: int, db: DbDep) -> ServerRosterSnapshot:
    return await get_roster_snapshot(db, game_id, ts)


@router.get("/{game_id}/rounds", response_model=RoundPage)
async def get_server_rounds(
    game_id: int,
    db: DbDep,
    before: int | None = Query(
        None, description="只取结束时间在这个 unix 秒之前的对局，传上一页的 next_before"
    ),
    limit: int = Query(30, ge=1, le=100),
) -> RoundPage:
    # 对局由生涯差分算出，服重启前后的实例合在一起，保留 90 天
    return await list_server_rounds(db, game_id, before=before, limit=limit)
