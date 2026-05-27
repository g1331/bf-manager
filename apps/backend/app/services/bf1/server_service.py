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
    ServerDetail,
    ServerListResponse,
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

            return ServerDetail(
                summary=summary,
                description=summary.description,
                settings=raw.get("settings") or raw.get("serverSettings") or {},
                map_rotation=rotation,
                players=players,
                raw=raw,
            )
