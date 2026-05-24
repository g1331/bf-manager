"""BF1 服务器查询服务"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
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
    return ServerSummary(
        server_id=int(server_info.get("serverId") or raw.get("serverId") or 0),
        game_id=int(server_info.get("gameId")) if server_info.get("gameId") else None,
        persisted_game_id=server_info.get("persistedGameId") or raw.get("persistedGameId"),
        name=server_info.get("name") or raw.get("name") or "",
        map_name=server_info.get("mapName") or raw.get("mapName"),
        game_mode=server_info.get("mode") or raw.get("gameMode") or raw.get("mode"),
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
        region=server_info.get("region") or raw.get("region"),
        is_official=bool(server_info.get("official") or raw.get("official") or False),
        is_ranked=bool(server_info.get("ranked") or raw.get("ranked") or False),
        has_password=bool(server_info.get("hasPassword") or raw.get("hasPassword") or False),
        description=server_info.get("description") or raw.get("description"),
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

            # 地图轮换
            rotation_raw = raw.get("rotation") or raw.get("serverInfo", {}).get("rotation") or []
            current_map = summary.map_name
            rotation = [
                MapRotationItem(
                    map_name=item.get("mapPrettyName") or item.get("mapName"),
                    game_mode=item.get("modePrettyName") or item.get("modeName"),
                    map_image_url=item.get("mapImage"),
                    is_current=(item.get("mapPrettyName") or item.get("mapName")) == current_map,
                )
                for item in rotation_raw
            ]

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
