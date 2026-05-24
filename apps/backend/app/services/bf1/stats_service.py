"""BF1 战绩查询服务"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.schemas.bf1.stats import (
    PlayerStatsDetail,
    PlayerStatsSummary,
    RecentServer,
    RecentServers,
    VehicleStat,
    VehicleStats,
    WeaponStat,
    WeaponStats,
)
from app.services.bf1.gateway_factory import get_bf1_client


def _safe(v: Any, default: Any = None) -> Any:
    if v is None:
        return default
    return v


class BF1StatsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_detailed_stats(self, persona_id: int) -> PlayerStatsDetail:
        async with get_bf1_client(self.db) as client:
            res = await client.detailedStatsByPersonaId(persona_id)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_STATS_FETCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            raw = res.get("result", {})
            basic = raw.get("basicStats", {}) or {}
            kills = int(_safe(basic.get("kills"), 0))
            deaths = int(_safe(basic.get("deaths"), 0))
            wins = int(_safe(basic.get("wins"), 0))
            losses = int(_safe(basic.get("losses"), 0))
            time_played = int(_safe(basic.get("timePlayed"), 0))
            spm = basic.get("spm")
            summary = PlayerStatsSummary(
                persona_id=persona_id,
                rank=int(_safe(basic.get("rank"), 0)) or None,
                sps=float(spm) / 60.0 if spm else None,
                kpm=float(_safe(basic.get("kpm"), 0)) or None,
                kd=(kills / deaths) if deaths > 0 else None,
                wins=wins,
                losses=losses,
                time_played_seconds=time_played,
                kills=kills,
                deaths=deaths,
            )
            return PlayerStatsDetail(summary=summary, raw=raw)

    async def get_weapons(self, persona_id: int) -> WeaponStats:
        async with get_bf1_client(self.db) as client:
            res = await client.getWeaponsByPersonaId(persona_id)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_WEAPONS_FETCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            raw = res.get("result") or []
            weapons: list[WeaponStat] = []
            for category in raw:
                cat_name = category.get("name") or category.get("category")
                for w in category.get("weapons") or []:
                    stats = w.get("stats", {}).get("values", {}) or {}
                    weapons.append(
                        WeaponStat(
                            name=w.get("name"),
                            category=cat_name,
                            kills=int(_safe(stats.get("kills"), 0)) or None,
                            headshots=int(_safe(stats.get("headshots"), 0)) or None,
                            accuracy=float(_safe(stats.get("accuracy"), 0)) or None,
                            time_seconds=float(_safe(stats.get("seconds"), 0)) or None,
                            image=w.get("imageUrl"),
                        )
                    )
            return WeaponStats(persona_id=persona_id, weapons=weapons)

    async def get_vehicles(self, persona_id: int) -> VehicleStats:
        async with get_bf1_client(self.db) as client:
            res = await client.getVehiclesByPersonaId(persona_id)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_VEHICLES_FETCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            raw = res.get("result") or []
            vehicles: list[VehicleStat] = []
            for category in raw:
                cat_name = category.get("name") or category.get("category")
                for v in category.get("vehicles") or []:
                    stats = v.get("stats", {}).get("values", {}) or {}
                    vehicles.append(
                        VehicleStat(
                            name=v.get("name"),
                            category=cat_name,
                            kills=int(_safe(stats.get("kills"), 0)) or None,
                            destroyed=int(_safe(stats.get("destroyed"), 0)) or None,
                            time_seconds=float(_safe(stats.get("seconds"), 0)) or None,
                            image=v.get("imageUrl"),
                        )
                    )
            return VehicleStats(persona_id=persona_id, vehicles=vehicles)

    async def get_recent_servers(self, persona_id: int) -> RecentServers:
        async with get_bf1_client(self.db) as client:
            res = await client.mostRecentServers(persona_id)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_RECENT_SERVERS_FETCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            raw = res.get("result") or []
            servers: list[RecentServer] = []
            for entry in raw:
                game_id_raw = entry.get("gameId")
                try:
                    server_id = int(game_id_raw) if game_id_raw is not None else None
                except (TypeError, ValueError):
                    server_id = None
                servers.append(
                    RecentServer(
                        name=entry.get("name", ""),
                        map_name=entry.get("mapNamePretty") or entry.get("mapName"),
                        game_mode=entry.get("mapModePretty") or entry.get("mapMode"),
                        last_played_at=None,
                        server_id=server_id,
                        persisted_game_id=entry.get("guid"),
                    )
                )
            return RecentServers(persona_id=persona_id, servers=servers)
