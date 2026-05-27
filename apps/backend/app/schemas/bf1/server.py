"""BF1 服务器 schema"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ServerSummary(BaseModel):
    """服务器列表项"""

    server_id: int
    game_id: int | None = None
    persisted_game_id: str | None = None
    name: str
    map_name: str | None = None
    map_display_name: str | None = None
    map_image_url: str | None = None
    game_mode: str | None = None
    mode_display_name: str | None = None
    player_count: int = 0
    max_player_count: int = 0
    queue_count: int = 0
    spectator_count: int = 0
    region: str | None = None
    region_display_name: str | None = None
    is_official: bool = False
    is_ranked: bool = False
    has_password: bool = False
    description: str | None = None


class ServerListResponse(BaseModel):
    """服务器列表"""

    total: int
    items: list[ServerSummary]


class MapRotationItem(BaseModel):
    map_name: str | None = None
    map_display_name: str | None = None
    game_mode: str | None = None
    mode_display_name: str | None = None
    map_image_url: str | None = None
    is_current: bool = False


class ServerPlayer(BaseModel):
    persona_id: int
    display_name: str
    team_id: int | None = None
    rank: int | None = None
    is_spectator: bool = False


class ServerDetail(BaseModel):
    """服务器详情"""

    summary: ServerSummary
    description: str | None = None
    settings: dict[str, Any] = {}
    map_rotation: list[MapRotationItem] = []
    players: list[ServerPlayer] = []
    raw: dict[str, Any] = {}
