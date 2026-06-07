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
    # ISO 国家代码（EA serverInfo.country，例如 "JP"）；官服多为空字符串，统一降为 None
    country: str | None = None
    # 服务器画面更新率 Hz（EA serverInfo.tickRate，常见 60/120）
    tick_rate: int | None = None
    # EA ping 节点代号（serverInfo.pingSiteAlias，类 IATA，例如 "nrt"=东京 "fra"=法兰克福）。
    # 游戏内 ping 是客户端到该数据中心节点的实测延迟，服务端拿不到数值，只能透传节点代号。
    ping_site: str | None = None
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


class BlazePlayerStats(BaseModel):
    """单个玩家的生涯综合战绩（来自 EA detailedStats，玩家列表按需合并）。

    全部允许为空：detailedStats 查询失败、限流或未开启战绩合并时该字段整体为 None，
    前端对应列显示占位。win_rate 为百分比（0-100），time_hours 为游玩时长（小时）。
    """

    win_rate: float | None = None
    kd: float | None = None
    kpm: float | None = None
    time_hours: float | None = None


class BlazePlayer(BaseModel):
    """Blaze roster 单个玩家。

    role 取 normal / queue / spectator；team 是 EA 原始 TIDX（0/1 为对阵两队，65535
    为排队或旁观）。is_admin / is_vip 由服务器 RSP 名单交叉得到，is_registered 表示该
    persona 已在本平台绑定（对应群版 UI 的「群友」高亮）。stats 仅在开启战绩合并时填充。
    """

    persona_id: int
    display_name: str
    rank: int = 0
    team: int = 65535
    latency: int = 0
    language: str | None = None
    join_time: float | None = None
    role: str = "normal"
    is_admin: bool = False
    is_vip: bool = False
    is_registered: bool = False
    stats: BlazePlayerStats | None = None


class BlazeTeamGroup(BaseModel):
    """一支队伍的玩家分组与聚合指标。

    faction 是阵营名称（如「法国」「德意志帝国」）；当前 Blaze 响应未提供可靠的阵营字段，
    暂留空由前端回退为「队伍 N」，待真实数据 dump 确认字段位置后再填充。
    """

    team_id: int
    faction: str | None = None
    players: list[BlazePlayer] = []
    count: int = 0
    rank_150_count: int = 0
    avg_rank: float | None = None


class ServerPlayersSummary(BaseModel):
    """玩家列表底部图例的计数：在线管理 / 在线 VIP / 在线群友 / 满级（150）数量。"""

    online_admin_count: int = 0
    online_vip_count: int = 0
    online_registered_count: int = 0
    rank_150_count: int = 0


class ServerPlayersResponse(BaseModel):
    """服务器实时玩家列表（Blaze roster + RSP 名单 + 可选生涯战绩）。"""

    game_id: int
    server_name: str | None = None
    max_players: int = 0
    player_count: int = 0
    queue_count: int = 0
    spectator_count: int = 0
    teams: list[BlazeTeamGroup] = []
    queued: list[BlazePlayer] = []
    spectators: list[BlazePlayer] = []
    summary: ServerPlayersSummary = ServerPlayersSummary()
    stats_included: bool = False
    is_mock: bool = False


class ServerOwner(BaseModel):
    """RSP 服主

    字段照 EA rspInfo.owner 原样透传：persona_id / platform_id / nucleus_id
    三个 ID + display_name + avatar + platform。
    EA persona DTO 的 accountId 字段是 Origin → Nucleus 账号统一前的历史遗留
    字段位，跨平台、跨独立社区实现采样全部为 "0"，不进 schema。
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
    """绑定到服务器的战队简介。emblem_url 占位符已展开为可加载 URL"""

    tag: str | None = None
    name: str | None = None
    size: int | None = None
    description: str | None = None
    emblem_url: str | None = None


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
