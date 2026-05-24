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


# BF1 每个 rank 对应的累计经验阈值（index = rank，最高 150）。
# EA basicStats.rank 长期不可靠（多数玩家返回 None），通过 spm * 游玩秒数 / 60
# 算出总经验，再在表里二分找区间得到等级。
_BF1_RANK_THRESHOLDS: tuple[int, ...] = (
    0, 1000, 5000, 15000, 25000, 40000, 55000, 75000, 95000, 120000,
    145000, 175000, 205000, 235000, 265000, 295000, 325000, 355000, 395000, 435000,
    475000, 515000, 555000, 595000, 635000, 675000, 715000, 755000, 795000, 845000,
    895000, 945000, 995000, 1045000, 1095000, 1145000, 1195000, 1245000, 1295000, 1345000,
    1405000, 1465000, 1525000, 1585000, 1645000, 1705000, 1765000, 1825000, 1885000, 1945000,
    2015000, 2085000, 2155000, 2225000, 2295000, 2365000, 2435000, 2505000, 2575000, 2645000,
    2745000, 2845000, 2945000, 3045000, 3145000, 3245000, 3345000, 3445000, 3545000, 3645000,
    3750000, 3870000, 4000000, 4140000, 4290000, 4450000, 4630000, 4830000, 5040000, 5260000,
    5510000, 5780000, 6070000, 6390000, 6730000, 7110000, 7510000, 7960000, 8430000, 8960000,
    9520000, 10130000, 10800000, 11530000, 12310000, 13170000, 14090000, 15100000, 16190000, 17380000,
    20000000, 20500000, 21000000, 21500000, 22000000, 22500000, 23000000, 23500000, 24000000, 24500000,
    25000000, 25500000, 26000000, 26500000, 27000000, 27500000, 28000000, 28500000, 29000000, 29500000,
    30000000, 30500000, 31000000, 31500000, 32000000, 32500000, 33000000, 33500000, 34000000, 34500000,
    35000000, 35500000, 36000000, 36500000, 37000000, 37500000, 38000000, 38500000, 39000000, 39500000,
    40000000, 41000000, 42000000, 43000000, 44000000, 45000000, 46000000, 47000000, 48000000, 49000000,
    50000000,
)  # fmt: skip


def _calc_rank_from_exp(spm: Any, time_played_seconds: Any) -> int | None:
    """根据 spm 和总游玩秒数推算 BF1 等级。spm/时间任一为空时返回 None。"""
    if not spm or not time_played_seconds:
        return None
    try:
        exp = float(spm) * float(time_played_seconds) / 60.0
    except (TypeError, ValueError):
        return None
    if exp <= 0:
        return 0
    if exp >= _BF1_RANK_THRESHOLDS[-1]:
        return len(_BF1_RANK_THRESHOLDS) - 1
    for i, threshold in enumerate(_BF1_RANK_THRESHOLDS):
        if exp <= threshold:
            return max(i - 1, 0)
    return 0


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
            ea_rank = int(_safe(basic.get("rank"), 0)) or None
            rank = ea_rank if ea_rank else _calc_rank_from_exp(spm, time_played)
            summary = PlayerStatsSummary(
                persona_id=persona_id,
                rank=rank,
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
                    hits = float(_safe(stats.get("hits"), 0))
                    shots = float(_safe(stats.get("shots"), 0))
                    # EA 上游会把 accuracy 截到 100；霰弹枪 / 投掷物的多弹丸命中应当 > 100，
                    # 因此用 hits/shots 自己算，绕开 EA 端的截断。
                    accuracy = (hits / shots * 100) if shots > 0 else None
                    weapons.append(
                        WeaponStat(
                            name=w.get("name"),
                            category=cat_name,
                            kills=int(_safe(stats.get("kills"), 0)) or None,
                            headshots=int(_safe(stats.get("headshots"), 0)) or None,
                            accuracy=accuracy,
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
