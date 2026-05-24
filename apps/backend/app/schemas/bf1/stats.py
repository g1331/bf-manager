"""BF1 战绩 schema"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PlayerStatsSummary(BaseModel):
    """生涯综合战绩（关键指标）"""

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


class PlayerStatsDetail(BaseModel):
    """完整战绩，包含 EA 原始 JSON（前端按需展示）"""

    summary: PlayerStatsSummary
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
