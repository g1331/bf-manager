"""BF1 战绩 schema"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlayerStatsSummary(BaseModel):
    """生涯综合战绩（关键指标）

    字段来自 EA detailedStats 的 result：基础值在 basicStats，战斗细分项
    （协助/复活/治疗/修理/狗牌/连杀/最远爆头）在 result 顶层，载具击杀按
    vehicleStats[].killsAs 求和、步战击杀为总击杀减载具击杀，最佳兵种取
    favoriteClass。缺失值为 None，前端按需展示。
    """

    persona_id: int
    display_name: str | None = None
    rank: int | None = None
    sps: float | None = None  # score per second
    kpm: float | None = None  # kills per minute
    kd: float | None = None  # kill/death
    wins: int | None = None
    losses: int | None = None
    time_played_seconds: int | None = None
    kills: int | None = None
    deaths: int | None = None
    # 扩展字段
    skill: float | None = None  # 技巧值（basicStats.skill）
    infantry_kills: int | None = None  # 步战击杀 = 总击杀 - 载具击杀
    vehicle_kills: int | None = None  # 载具击杀 = sum(vehicleStats[].killsAs)
    assists: int | None = None  # 协助击杀（killAssists）
    revives: int | None = None  # 复活数（revives）
    heals: int | None = None  # 治疗数（heals）
    repairs: int | None = None  # 修理数（repairs）
    dogtags: int | None = None  # 狗牌数（dogtagsTaken）
    max_killstreak: int | None = None  # 最高连杀（highestKillStreak）
    longest_headshot_meters: float | None = None  # 最远爆头（longestHeadShot）
    best_class: str | None = None  # 最佳兵种代号（小写，来自 favoriteClass）


class SoldierClassStat(BaseModel):
    """单个兵种的战绩，来自 EA detailedStats.result.kitStats[]

    EA 返回七个兵种，name 为英文代号 Assault/Support/Medic/Scout/Tanker/
    Cavalry/Pilot；本 schema 把它转小写后用 JSON key "class" 暴露，与前端
    兵种代号对齐。
    """

    class_name: str = Field(serialization_alias="class")  # 兵种代号（小写）
    kills: int = 0
    score: int = 0
    time_seconds: int = 0  # 来自 kitStats[].secondsAs


class PlayerStatsDetail(BaseModel):
    """完整战绩，包含兵种分布与 EA 原始 JSON（前端按需展示）"""

    summary: PlayerStatsSummary
    soldiers: list[SoldierClassStat] = []
    raw: dict[str, Any]


class WeaponStat(BaseModel):
    name: str | None = None
    category: str | None = None
    kills: int | None = None
    headshots: int | None = None
    accuracy: float | None = None
    time_seconds: float | None = None
    image: str | None = None


class WeaponStats(BaseModel):
    persona_id: int
    weapons: list[WeaponStat]


class VehicleStat(BaseModel):
    name: str | None = None
    category: str | None = None
    kills: int | None = None
    destroyed: int | None = None
    time_seconds: float | None = None
    image: str | None = None


class VehicleStats(BaseModel):
    persona_id: int
    vehicles: list[VehicleStat]


class RecentServer(BaseModel):
    name: str
    map_name: str | None = None
    game_mode: str | None = None
    last_played_at: str | None = None
    server_id: int | None = None
    persisted_game_id: str | None = None


class RecentServers(BaseModel):
    persona_id: int
    servers: list[RecentServer]


class OnlineStatus(BaseModel):
    """玩家当前在线状态。

    来自 EA GameServer.getServersByPersonaIds：result 中该 pid 的值为某服务器
    信息时即在线，值为 null 时离线。is_online 为 None 表示上游查询失败或返回
    结构异常，无法判定（前端据此隐藏在线标识，而非误判为离线）。
    """

    persona_id: int
    is_online: bool | None = None
    server_name: str | None = None  # 在线时所在服务器名（若 EA 返回中可得）


class PlayerPlatoon(BaseModel):
    """玩家当前所属战队，来自 EA Platoons.getActivePlatoon。

    与服务器维度的 server.PlatoonBrief 区分：玩家页需要徽章图与 guid，故单列。
    EA result 为 null 时表示玩家未加入战队，service 层返回 None。emblem_url 是把
    EA emblem 占位符（[SIZE]/[FORMAT]）展开后的可加载 URL。
    """

    guid: str | None = None
    tag: str | None = None
    name: str | None = None
    size: int | None = None  # 战队人数（EA result.size）
    description: str | None = None
    emblem_url: str | None = None  # 徽章图（占位符已展开）
    verified: bool = False  # EA 官方认证战队
