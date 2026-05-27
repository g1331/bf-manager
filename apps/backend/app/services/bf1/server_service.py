"""BF1 服务器查询服务"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
from app.domain.games.bf1.maps import (
    normalize_map_image_url,
    translate_map_name,
    translate_mode_name,
    translate_region,
)
from app.schemas.bf1.server import (
    MapRotationItem,
    PlatoonBrief,
    ServerDetail,
    ServerExtras,
    ServerLifecycle,
    ServerListResponse,
    ServerMember,
    ServerOwner,
    ServerPlayer,
    ServerSummary,
)
from app.services.bf1.gateway_factory import get_bf1_client


def _to_summary(raw: dict[str, Any]) -> ServerSummary:
    server_info = raw.get("serverInfo") or raw
    map_name = server_info.get("mapName") or raw.get("mapName")
    game_mode = server_info.get("mode") or raw.get("gameMode") or raw.get("mode")
    region = server_info.get("region") or raw.get("region")
    map_image_url = (
        server_info.get("mapImageUrl")
        or raw.get("mapImageUrl")
        or server_info.get("mapImage")
        or raw.get("mapImage")
    )
    return ServerSummary(
        server_id=int(server_info.get("serverId") or raw.get("serverId") or 0),
        game_id=int(server_info.get("gameId")) if server_info.get("gameId") else None,
        persisted_game_id=server_info.get("persistedGameId") or raw.get("persistedGameId"),
        name=server_info.get("name") or raw.get("name") or "",
        map_name=map_name,
        map_display_name=translate_map_name(map_name),
        map_image_url=normalize_map_image_url(map_image_url),
        game_mode=game_mode,
        mode_display_name=translate_mode_name(game_mode),
        player_count=int(
            server_info.get("slots", {}).get("Soldier", {}).get("current")
            or raw.get("slots", {}).get("Soldier", {}).get("current")
            or 0
        ),
        max_player_count=int(
            server_info.get("slots", {}).get("Soldier", {}).get("max")
            or raw.get("slots", {}).get("Soldier", {}).get("max")
            or 0
        ),
        queue_count=int(
            server_info.get("slots", {}).get("Queue", {}).get("current")
            or raw.get("slots", {}).get("Queue", {}).get("current")
            or 0
        ),
        spectator_count=int(
            server_info.get("slots", {}).get("Spectator", {}).get("current")
            or raw.get("slots", {}).get("Spectator", {}).get("current")
            or 0
        ),
        region=region,
        region_display_name=translate_region(region),
        is_official=bool(server_info.get("official") or raw.get("official") or False),
        is_ranked=bool(server_info.get("ranked") or raw.get("ranked") or False),
        has_password=bool(server_info.get("hasPassword") or raw.get("hasPassword") or False),
        description=server_info.get("description") or raw.get("description"),
    )


def _to_rotation(raw: dict[str, Any]) -> list[MapRotationItem]:
    """从详情接口 raw 字典里拼装地图轮换列表。

    is_current 判定显式比较「内部代号」字段（serverInfo.mapName vs item.mapName），
    不依赖 summary.map_name 这种可能混入 prettyName 的字段，避免代号与
    prettyName 错位导致整局都不命中。current_code 为空时跳过判定。
    """
    rotation_raw = raw.get("rotation") or raw.get("serverInfo", {}).get("rotation") or []
    server_info = raw.get("serverInfo") or {}
    current_map_code = server_info.get("mapName") or raw.get("mapName")
    rotation: list[MapRotationItem] = []
    for item in rotation_raw:
        item_code = item.get("mapName")
        item_map_name = item_code or item.get("mapPrettyName")
        item_mode_name = item.get("modeName") or item.get("modePrettyName")
        rotation.append(
            MapRotationItem(
                map_name=item_map_name,
                map_display_name=translate_map_name(item_code) or item.get("mapPrettyName"),
                game_mode=item_mode_name,
                mode_display_name=translate_mode_name(item.get("modeName"))
                or item.get("modePrettyName"),
                map_image_url=normalize_map_image_url(item.get("mapImage")),
                is_current=bool(current_map_code) and item_code == current_map_code,
            )
        )
    return rotation


def _to_member(item: dict[str, Any]) -> ServerMember | None:
    """rspInfo.adminList / vipList / bannedList 中单项 → ServerMember

    EA 字段名为 personaId（字符串）。无法解析 persona_id 时返回 None，由调用方过滤。
    accountId 一般为占位 "0"，不进 schema。
    """
    raw_pid = item.get("personaId") or item.get("personaID")
    try:
        persona_id = int(raw_pid) if raw_pid is not None else 0
    except (TypeError, ValueError):
        return None
    if persona_id == 0:
        return None
    return ServerMember(
        persona_id=persona_id,
        display_name=item.get("displayName") or item.get("name"),
        avatar_url=item.get("avatar"),
        platform=item.get("platform"),
        platform_id=item.get("platformId"),
        nucleus_id=item.get("nucleusId"),
    )


def _to_extras(raw: dict[str, Any]) -> ServerExtras:
    """从 getFullServerDetails.result 拼装扩展信息。

    rspInfo 缺失时只回填 serverInfo 已有的 game_id / persisted_game_id / 收藏数；
    时间戳由 ServerLifecycle 的 field_validator 统一转换，非法值降为 None。
    """
    server_info = raw.get("serverInfo") or {}
    rsp_info = raw.get("rspInfo") or {}
    platoon_info = raw.get("platoonInfo") or None

    rsp_server = rsp_info.get("server") or {}
    owner_raw = rsp_info.get("owner") or None

    game_id_raw = server_info.get("gameId") or raw.get("gameId")
    try:
        game_id = int(game_id_raw) if game_id_raw is not None else None
    except (TypeError, ValueError):
        game_id = None
    server_id_raw = rsp_server.get("serverId") or server_info.get("serverId")
    try:
        server_id = int(server_id_raw) if server_id_raw is not None else None
    except (TypeError, ValueError):
        server_id = None
    persisted_game_id = (
        server_info.get("persistedGameId") or raw.get("persistedGameId") or server_info.get("guid")
    )

    bookmark_count_raw = server_info.get("serverBookmarkCount")
    try:
        bookmark_count = int(bookmark_count_raw) if bookmark_count_raw is not None else None
    except (TypeError, ValueError):
        bookmark_count = None

    owner: ServerOwner | None = None
    if owner_raw:
        owner_pid_raw = owner_raw.get("personaId")
        try:
            owner_pid = int(owner_pid_raw) if owner_pid_raw is not None else None
        except (TypeError, ValueError):
            owner_pid = None
        owner = ServerOwner(
            persona_id=owner_pid,
            display_name=owner_raw.get("displayName"),
            avatar_url=owner_raw.get("avatar"),
            platform=owner_raw.get("platform"),
            platform_id=owner_raw.get("platformId"),
            nucleus_id=owner_raw.get("nucleusId"),
        )

    lifecycle = ServerLifecycle(
        created_at=rsp_server.get("createdDate"),
        expires_at=rsp_server.get("expirationDate"),
        updated_at=rsp_server.get("updatedDate"),
    )

    admins = [m for m in (_to_member(a) for a in rsp_info.get("adminList") or []) if m]
    vips = [m for m in (_to_member(v) for v in rsp_info.get("vipList") or []) if m]
    banned = [m for m in (_to_member(b) for b in rsp_info.get("bannedList") or []) if m]

    platoon: PlatoonBrief | None = None
    if platoon_info:
        size_raw = platoon_info.get("size")
        try:
            size = int(size_raw) if size_raw is not None else None
        except (TypeError, ValueError):
            size = None
        platoon = PlatoonBrief(
            tag=platoon_info.get("tag"),
            name=platoon_info.get("name"),
            size=size,
            description=platoon_info.get("description"),
        )

    return ServerExtras(
        game_id=game_id,
        server_id=server_id,
        persisted_game_id=persisted_game_id,
        bookmark_count=bookmark_count,
        owner=owner,
        lifecycle=lifecycle,
        admins=admins,
        vips=vips,
        banned=banned,
        platoon=platoon,
    )


class BF1ServerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(
        self,
        keyword: str | None = None,
        *,
        limit: int = 50,
    ) -> ServerListResponse:
        async with get_bf1_client(self.db) as client:
            res = await client.searchServers(
                server_name=keyword or "",
                limit=limit,
            )
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_SERVER_SEARCH_FAILED",
                    message=f"EA Gateway 服务器搜索失败: {res}",
                )
            raw = res.get("result", {})
            game_servers = raw.get("gameservers") or []
            items = [_to_summary(s) for s in game_servers]
            return ServerListResponse(total=len(items), items=items)

    async def get_detail(self, game_id: int) -> ServerDetail:
        async with get_bf1_client(self.db) as client:
            res = await client.getFullServerDetails(game_id)
            if not isinstance(res, dict):
                # 退化到 getServerDetails
                res = await client.getServerDetails(game_id)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_SERVER_DETAIL_FAILED",
                    message=f"EA Gateway 服务器详情失败: {res}",
                )
            raw = res.get("result") or {}
            if not raw:
                raise NotFoundError(resource=f"服务器 gameId={game_id}")

            summary = _to_summary(raw)
            rotation = _to_rotation(raw)

            # 玩家列表（从 servers detail 的 teams 拼出）
            teams = raw.get("teams") or []
            players: list[ServerPlayer] = []
            for team_idx, team in enumerate(teams, start=1):
                for p in team.get("players") or []:
                    persona_id = int(p.get("personaId") or p.get("personaID") or 0)
                    if persona_id == 0:
                        continue
                    players.append(
                        ServerPlayer(
                            persona_id=persona_id,
                            display_name=p.get("name") or p.get("displayName") or "",
                            team_id=p.get("team") or team_idx,
                            rank=p.get("rank"),
                            is_spectator=False,
                        )
                    )
            # 旁观者
            for spec in raw.get("spectators") or []:
                persona_id = int(spec.get("personaId") or spec.get("personaID") or 0)
                if persona_id == 0:
                    continue
                players.append(
                    ServerPlayer(
                        persona_id=persona_id,
                        display_name=spec.get("name") or spec.get("displayName") or "",
                        team_id=None,
                        rank=spec.get("rank"),
                        is_spectator=True,
                    )
                )

            settings = (
                raw.get("settings")
                or raw.get("serverSettings")
                or raw.get("serverInfo", {}).get("settings")
                or {}
            )
            extras = _to_extras(raw)
            return ServerDetail(
                summary=summary,
                description=summary.description,
                settings=settings,
                map_rotation=rotation,
                players=players,
                extras=extras,
                raw=raw,
            )
