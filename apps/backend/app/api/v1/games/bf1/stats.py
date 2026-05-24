"""BF1 战绩路由"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.schemas.bf1.stats import (
    PlayerStatsDetail,
    RecentServers,
    VehicleStats,
    WeaponStats,
)
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
