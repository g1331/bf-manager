"""BF1 战绩 schema"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlayerStatsSummary(BaseModel):
    """生涯综合战绩（关键指标）

    字段来自 Blaze Stats.getStats（映射见 domain/games/bf1/blaze_stats.py）：载具击杀为
    All Vehicles 击杀、步战击杀为总击杀减载具击杀，最佳兵种为在场时间最长的兵种。
    缺失值为 None，前端按需展示。
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
    skill: float | None = None  # 技巧值
    infantry_kills: int | None = None  # 步战击杀 = 总击杀 - 载具击杀
    vehicle_kills: int | None = None  # 载具击杀（含船只与巨兽）
    assists: int | None = None  # 协助击杀
    revives: int | None = None  # 复活数
    heals: int | None = None  # 治疗数
    repairs: int | None = None  # 修理数
    dogtags: int | None = None  # 狗牌数
    max_killstreak: int | None = None  # 最高连杀
    longest_headshot_meters: float | None = None  # 最远爆头
    best_class: str | None = None  # 最佳兵种代号（小写）


class SoldierClassStat(BaseModel):
    """单个兵种的战绩（Blaze），七个兵种 assault/support/medic/scout/tanker/cavalry/pilot，
    用 JSON key "class" 暴露，与前端兵种代号对齐。
    """

    class_name: str = Field(serialization_alias="class")  # 兵种代号（小写）
    kills: int = 0
    score: int = 0
    time_seconds: int = 0  # 在场秒数


class CareerHonors(BaseModel):
    mvp: int = 0  # 拿过几次 MVP
    ace_squad: int = 0  # 进过几次王牌小队
    ribbons: int = 0  # 勋带总数
    medals: int = 0  # 勋章数


class CareerCombat(BaseModel):
    headshots: int = 0
    shots: int = 0
    hits: int = 0
    accuracy: float | None = None  # 命中 ÷ 开火
    headshot_rate: float | None = None  # 爆头 ÷ 击杀
    avenger_kills: int = 0  # 复仇击杀
    savior_kills: int = 0  # 救星击杀
    nemesis_kills: int = 0  # 宿敌击杀
    max_nemesis_streak: int = 0  # 最高宿敌连杀
    squad_wipes: int = 0  # 团灭
    vehicles_destroyed: int = 0  # 摧毁载具


class CareerTeamwork(BaseModel):
    resupplies: int = 0
    spot_assists: int = 0
    suppression_assists: int = 0
    squad_spawns: int = 0
    orders_completed: int = 0
    squad_kill_assists: int = 0
    flag_captures: int = 0
    flag_defends: int = 0


class CareerMode(BaseModel):
    """一个模式的胜负与目标得分。mode：conquest / operations / rush / frontlines / domination /
    war_pigeons / team_deathmatch / air_assault"""

    mode: str
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None  # 0-1
    score: int | None = Field(
        default=None,
        description="这个模式里的目标得分（占点、炸弹、信鸽等），不含击杀、团队、小队分；空中突击为 null",
    )


class EliteKitStat(BaseModel):
    """精英兵：sentry / flamethrower / trench_raider / tank_hunter / infiltrator"""

    kit: str
    kills: int | None = Field(default=None, description="EA 这次没返回这项时为 null")
    time_seconds: int = 0


class CareerMap(BaseModel):
    map: str  # 地图代号（MP_*）
    time_seconds: int


class CareerRibbon(BaseModel):
    code: str  # 图鉴 ribbons 的 code（r01…r47）
    count: int


class CareerMisc(BaseModel):
    rounds_completed: int = 0  # 打到结算的局数
    rounds_played: int = 0  # 参与的局数（含中途退出）
    completion_rate: float | None = None  # 0-1
    spectator_seconds: int = 0  # 观战时长


class PlayerStatsDetail(BaseModel):
    """完整战绩，包含兵种分布与 Blaze 原始统计 {统计名: 数值}（前端按需展示）

    honors 起的几组是战绩页的扩展（2026-11 起），缓存 10 分钟；ribbons 为 None 表示勋带类别
    没读到，次数为 0 的勋带也列出（勋带墙要置灰）。
    """

    summary: PlayerStatsSummary
    soldiers: list[SoldierClassStat] = []
    honors: CareerHonors | None = None
    combat: CareerCombat | None = None
    teamwork: CareerTeamwork | None = None
    modes: list[CareerMode] = []
    elite_kits: list[EliteKitStat] = []
    maps: list[CareerMap] | None = Field(
        default=None, description="玩过的地图，按时长倒序；EA 这次没返回全部地图统计时为 null"
    )
    ribbons: list[CareerRibbon] | None = None
    misc: CareerMisc | None = None
    raw: dict[str, Any]


class WeaponStat(BaseModel):
    name: str | None = None
    category: str | None = None
    kills: int | None = None
    headshots: int | None = None
    accuracy: float | None = None
    time_seconds: float | None = None
    image: str | None = None
    skin_name: str | None = None
    # 原样下发上游稀有度名（Superior / Enhanced / Standard），由前端归一着色
    skin_rarity: str | None = None
    skin_image: str | None = None


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
    skin_name: str | None = None
    skin_rarity: str | None = None
    skin_image: str | None = None


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
    game_id: int | None = None  # 在线时所在服务器的 gameId，用来跳转服务器详情


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
