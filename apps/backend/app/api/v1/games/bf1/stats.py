"""BF1 战绩路由"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.schemas.bf1.ban import BanStatus
from app.schemas.bf1.stats import (
    OnlineStatus,
    PlayerPlatoon,
    PlayerStatsDetail,
    RecentServers,
    VehicleStats,
    WeaponStats,
)
from app.services.bf1.ban_service import BF1BanService
from app.services.bf1.stats_service import BF1StatsService

router = APIRouter()


@router.get("/{persona_id}", response_model=PlayerStatsDetail)
async def get_stats(persona_id: int, db: DbDep) -> PlayerStatsDetail:
    return await BF1StatsService(db).get_detailed_stats(persona_id)


@router.get("/{persona_id}/weapons", response_model=WeaponStats)
async def get_weapons(persona_id: int, db: DbDep) -> WeaponStats:
    return await BF1StatsService(db).get_weapons(persona_id)


@router.get("/{persona_id}/vehicles", response_model=VehicleStats)
async def get_vehicles(persona_id: int, db: DbDep) -> VehicleStats:
    return await BF1StatsService(db).get_vehicles(persona_id)


@router.get("/{persona_id}/recent-servers", response_model=RecentServers)
async def get_recent_servers(persona_id: int, db: DbDep) -> RecentServers:
    return await BF1StatsService(db).get_recent_servers(persona_id)


@router.get("/{persona_id}/online", response_model=OnlineStatus)
async def get_online(persona_id: int, db: DbDep) -> OnlineStatus:
    return await BF1StatsService(db).get_online_status(persona_id)


@router.get("/{persona_id}/platoon", response_model=PlayerPlatoon | None)
async def get_platoon(persona_id: int, db: DbDep) -> PlayerPlatoon | None:
    # 玩家未加入战队时返回 null，前端据此隐藏战队展示
    return await BF1StatsService(db).get_platoon(persona_id)


@router.get("/{persona_id}/ban", response_model=BanStatus)
async def get_ban(
    persona_id: int,
    name: str | None = Query(None, description="EA 昵称，BFEAC 按昵称查询时需要"),
) -> BanStatus:
    return await BF1BanService().get_ban_status(persona_id, name)
