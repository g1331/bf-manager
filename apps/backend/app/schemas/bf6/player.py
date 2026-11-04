"""BF6 玩家与战绩 schema。

数值都来自 EA 客户端网关 ``getStats`` 的 ``global`` 维度（生涯），None 表示 EA 没给这一项
（玩家没用过这把武器、没玩过这个模式），不是 0。比率字段由服务端算出。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Bf6PlatformParam = Literal["ea", "psn", "xbox", "steam", "epic"]


class Bf6ResolvedPlayer(BaseModel):
    nucleus_id: int
    display_name: str | None = None
    # Drop API 的命名空间：cem_ea_id / ps3 / xbox / epic
    platform: str | None = None
    avatar_url: str | None = None
    has_current_season_stats: bool


class Bf6Career(BaseModel):
    # Kills_Total：含击杀 AI；K/D、KPM 用 human_kills
    kills: int | None = None
    human_kills: int | None = None
    deaths: int | None = None
    score: int | None = None
    matches: int | None = None
    wins: int | None = None
    losses: int | None = None
    # tp_kit：实际在场上的战斗时间，SPM/KPM/时长都按它算
    time_seconds: int | None = None
    shots_fired: int | None = None
    shots_hit: int | None = None
    headshots: int | None = None
    longest_killstreak: int | None = None
    damage: int | None = None
    assists: int | None = None
    revives: int | None = None
    captures: int | None = None
    vehicles_destroyed: int | None = None
    repairs: int | None = None
    healing: int | None = None
    vehicle_kills: int | None = None
    melee_kills: int | None = None
    distance_m: int | None = None

    kd: float | None = None
    kpm: float | None = None
    spm: float | None = None
    win_rate: float | None = None
    accuracy: float | None = None
    headshot_rate: float | None = None
    best_class: str | None = None


class Bf6WeaponStats(BaseModel):
    # 内部 ID，如 mg_l110；中文名表到位前前端直接显示
    id: str
    kills: int | None = None
    damage: int | None = None
    shots_fired: int | None = None
    shots_hit: int | None = None
    headshots: int | None = None
    time_seconds: int | None = None
    hipfire_kills: int | None = None
    ads_kills: int | None = None
    accuracy: float | None = None
    headshot_rate: float | None = None
    kpm: float | None = None


class Bf6VehicleStats(BaseModel):
    id: str
    kills: int | None = None
    damage: int | None = None
    time_seconds: int | None = None
    distance_m: int | None = None
    spawns: int | None = None
    kpm: float | None = None


class Bf6KitStats(BaseModel):
    id: str
    kills: int | None = None
    deaths: int | None = None
    score: int | None = None
    time_seconds: int | None = None
    spawns: int | None = None
    revives: int | None = None
    kd: float | None = None


class Bf6ModeStats(BaseModel):
    id: str
    kills: int | None = None
    matches: int | None = None
    wins: int | None = None
    losses: int | None = None
    score: int | None = None
    time_seconds: int | None = None
    win_rate: float | None = None


class Bf6MapStats(BaseModel):
    # 统计名里 lvl 之后的部分：mpaftermath（多人地图）、ftpgranite（大逃杀）……
    id: str
    matches: int | None = None
    wins: int | None = None
    losses: int | None = None
    time_seconds: int | None = None
    win_rate: float | None = None


class Bf6PlayerStats(BaseModel):
    nucleus_id: int
    # EA 有没有返回这名玩家的多人统计；False 时页面显示“无数据”而不是一排 0
    has_data: bool
    career: Bf6Career
    weapons: list[Bf6WeaponStats]
    # 武器大类汇总（突击步枪、冲锋枪……），id 为 ar / smg 这类
    weapon_categories: list[Bf6WeaponStats]
    vehicles: list[Bf6VehicleStats]
    vehicle_categories: list[Bf6VehicleStats]
    kits: list[Bf6KitStats]
    modes: list[Bf6ModeStats]
    # EA 的地图统计只有场次、胜负和时长，没有击杀
    maps: list[Bf6MapStats]
    fetched_at: datetime
