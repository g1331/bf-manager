"""BF1 服务器 schema"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_validator


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


class ServerOwner(BaseModel):
    """RSP 服主

    字段直接对应 EA rspInfo.owner 的公开字段：persona 标识三件套
    （persona_id / platform_id / nucleus_id）+ display_name + avatar + platform。
    accountId 一般为占位字符串 "0"，无业务价值，不进 schema。
    """

    persona_id: int | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    nucleus_id: str | None = None


class ServerMember(BaseModel):
    """admin / vip / banned 列表项

    与 ServerOwner 同字段集，复用于 rspInfo.adminList / vipList / bannedList。
    persona_id 解析失败的项由 _to_member 过滤掉，不进列表。
    """

    persona_id: int
    display_name: str | None = None
    avatar_url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    nucleus_id: str | None = None


class ServerLifecycle(BaseModel):
    """RSP server 生命周期时间戳

    EA 返回毫秒级 unix 时间戳的字符串，统一在 validator 里转 UTC datetime；
    非法值（缺失 / 空 / 非数值）一律降为 None，service 不做判断。
    """

    created_at: datetime | None = None
    expires_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("created_at", "expires_at", "updated_at", mode="before")
    @classmethod
    def _coerce_epoch_ms(cls, v: Any) -> datetime | None:
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v
        try:
            ms = int(v)
        except (TypeError, ValueError):
            return None
        try:
            return datetime.fromtimestamp(ms / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None


class PlatoonBrief(BaseModel):
    """绑定到服务器的战队简介"""

    tag: str | None = None
    name: str | None = None
    size: int | None = None
    description: str | None = None


class ServerExtras(BaseModel):
    """服务器扩展信息：服主 / 生命周期 / 收藏 / 战队 / admin&vip 名单 / ban 计数"""

    game_id: int | None = None
    server_id: int | None = None
    persisted_game_id: str | None = None
    bookmark_count: int | None = None
    owner: ServerOwner | None = None
    lifecycle: ServerLifecycle = ServerLifecycle()
    admins: list[ServerMember] = []
    vips: list[ServerMember] = []
    banned: list[ServerMember] = []
    platoon: PlatoonBrief | None = None


class ServerDetail(BaseModel):
    """服务器详情"""

    summary: ServerSummary
    description: str | None = None
    settings: dict[str, Any] = {}
    map_rotation: list[MapRotationItem] = []
    players: list[ServerPlayer] = []
    extras: ServerExtras = ServerExtras()
    raw: dict[str, Any] = {}
