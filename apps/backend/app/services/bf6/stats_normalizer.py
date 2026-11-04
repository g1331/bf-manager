"""把 getStats 的扁平统计行整理成生涯 / 武器 / 载具 / 兵种 / 模式 / 赛季。

``glacier_mp`` 里每个统计名按维度出多行：``{global: global}`` 是生涯，``{GameMode}`` 是该模式生涯，
``{GameMode, Season[, GameType]}`` 是该模式该赛季；这里只请求 global 维度。武器、载具这类明细没有单独维度，
是用统计名前缀区分的（``kw_wp_mg_l110`` = 机枪 L110 的击杀），所以按前缀拆。
EA 只返回玩家用过的条目，没用过的武器没有行。

口径：
- ``Kills_Total`` 含 AI，``human_kills_total`` 只算真人；K/D、KPM 用后者。``kills_gm_all`` 又是另一套
  口径（含载具、事件计数），不和前两者混用。
- 时长用 ``tp_kit``（实际战斗时间）；``tp_gm_all`` 是在模式里的时间，偏大。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.domain.games.bf6.client import STATS_CATEGORY
from app.domain.games.bf6.wire import DimensionedStat, PlayerStats
from app.schemas.bf6.player import (
    Bf6Career,
    Bf6KitStats,
    Bf6MapStats,
    Bf6ModeStats,
    Bf6PlayerStats,
    Bf6VehicleStats,
    Bf6WeaponStats,
)

_CAREER_FIELDS = {
    "kills": "Kills_Total",
    "human_kills": "human_kills_total",
    "deaths": "deaths_total",
    "score": "score_total",
    "matches": "matches_gm_all",
    "wins": "wins_gm_all",
    "losses": "losses_gm_all",
    "time_seconds": "tp_kit",
    "shots_fired": "shots_fired_total",
    "shots_hit": "shots_hit_total",
    "headshots": "kills_Headshots_Total",
    "longest_killstreak": "killstreak_longest_Total",
    "damage": "Dmg_Dealt_Total",
    "assists": "Assist_Total",
    "revives": "Revives_Teammates_Total",
    "captures": "Obj_Captured_Total",
    "vehicles_destroyed": "Destroyed_Veh_Total",
    "repairs": "Veh_RepairedHP_Total",
    "healing": "Dmg_Healed_Total",
    "vehicle_kills": "kw_veh",
    "melee_kills": "Kills_Melee_Total",
}

_WEAPON_PREFIXES = {
    "kills": "kw_wp_",
    "damage": "dmg_wp_",
    "shots_fired": "sfw_wp_",
    "shots_hit": "shw_wp_",
    "headshots": "hsw_wp_",
    "time_seconds": "tp_wp_",
    "hipfire_kills": "hfkw_wp_",
    "ads_kills": "adskw_wp_",
}
# 武器前缀下的大类汇总行；手枪的汇总叫 pst_temp，统一成 pst
_WEAPON_CATEGORIES = {"ar", "crb", "smg", "mg", "snp", "sg", "dmr", "pst"}
_WEAPON_CATEGORY_ALIASES = {"pst_temp": "pst"}
# temp 是全部武器合计，和大类汇总重复，不单列
_WEAPON_TOTAL = "temp"

_VEHICLE_PREFIXES = {
    "kills": "kw_veh_",
    "damage": "dmg_veh_",
    "time_seconds": "tp_veh_",
    "distance_m": "disttrv_veh_",
    "spawns": "spawns_veh_",
}
# 载具前缀下的汇总行：空中 / 地面 / 水面，以及直升机、喷气机两个子类
_VEHICLE_CATEGORIES = {"air", "sur", "nav", "air_helis", "air_jets"}

_KIT_PREFIXES = {
    "kills": "kw_kit_",
    "deaths": "deaths_kit_",
    "score": "scoreas_kit_",
    "time_seconds": "tp_kit_",
    "spawns": "spawns_kit_",
    "revives": "revives_kit_",
}

_MODE_PREFIXES = {
    "kills": "kills_gm_",
    "matches": "matches_gm_",
    "wins": "wins_gm_",
    "losses": "losses_gm_",
    "score": "scorein_gm_",
    "time_seconds": "tp_gm_",
}
# 模式前缀下的汇总行，不是具体模式
_MAP_PREFIXES = {
    "matches": "matches_lvl",
    "wins": "wins_lvl",
    "losses": "losses_lvl",
    "time_seconds": "tp_lvl",
}
# lvlmp 是全部多人地图合计，lvlftp 是免费模式合计
_MAP_AGGREGATES = {"mp", "ftp"}

# oblitall、rr_all 是同一玩法几个变体的合计；modbuilder0 与 modbuilder 数值相同
_MODE_AGGREGATES = {"all", "official", "mp", "oblitall", "rr_all", "modbuilder0"}


def ratio(numerator: int | None, denominator: float | None, digits: int = 4) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator, digits)


def _per_minute(value: int | None, seconds: int | None) -> float | None:
    return ratio(value, seconds / 60 if seconds else None, 3)


def _group(stats: dict[str, int], prefixes: dict[str, str]) -> dict[str, dict[str, int | None]]:
    """按前缀把 ``<prefix><id>`` 拆成 {id: {字段: 值}}；某个前缀下没有这一项的字段为 None。"""
    ids: set[str] = set()
    for prefix in prefixes.values():
        ids.update(name[len(prefix) :] for name in stats if name.startswith(prefix))
    ids.discard("")
    return {
        item: {key: stats.get(prefix + item) for key, prefix in prefixes.items()} for item in ids
    }


def _desc[T: BaseModel](rows: list[T], key: str) -> list[T]:
    return sorted(rows, key=lambda row: getattr(row, key) or 0, reverse=True)


def _dims(stat: DimensionedStat) -> dict[str, str]:
    return {dim.key: dim.value for dim in stat.dimensions}


def normalize(player: PlayerStats | None, nucleus_id: int, fetched_at: datetime) -> Bf6PlayerStats:
    """player 为 None 表示 EA 没返回这名玩家。"""
    categories = player.categories if player else ()
    category = next((c for c in categories if c.category_id == STATS_CATEGORY), None)
    rows = category.dimensioned_stats if category else ()

    stats: dict[str, int] = {}
    for row in rows:
        dims = _dims(row)
        if dims == {"global": "global"}:
            stats[row.name] = row.value

    career = Bf6Career.model_validate(
        {key: stats.get(name) for key, name in _CAREER_FIELDS.items()}
    )
    foot, vehicle = stats.get("distrav_foot_total"), stats.get("distrav_veh_total")
    if foot is not None or vehicle is not None:
        career.distance_m = (foot or 0) + (vehicle or 0)
    career.kd = ratio(career.human_kills, career.deaths)
    career.kpm = _per_minute(career.human_kills, career.time_seconds)
    career.spm = _per_minute(career.score, career.time_seconds)
    career.win_rate = ratio(career.wins, career.matches)
    career.accuracy = ratio(career.shots_hit, career.shots_fired)
    career.headshot_rate = ratio(career.headshots, career.kills)

    weapons: list[Bf6WeaponStats] = []
    weapon_categories: list[Bf6WeaponStats] = []
    for raw_id, values in _group(stats, _WEAPON_PREFIXES).items():
        if raw_id == _WEAPON_TOTAL:
            continue
        item = _WEAPON_CATEGORY_ALIASES.get(raw_id, raw_id)
        weapon = Bf6WeaponStats.model_validate({"id": item, **values})
        weapon.accuracy = ratio(weapon.shots_hit, weapon.shots_fired)
        weapon.headshot_rate = ratio(weapon.headshots, weapon.kills)
        weapon.kpm = _per_minute(weapon.kills, weapon.time_seconds)
        (weapon_categories if item in _WEAPON_CATEGORIES else weapons).append(weapon)

    vehicles: list[Bf6VehicleStats] = []
    vehicle_categories: list[Bf6VehicleStats] = []
    for item, values in _group(stats, _VEHICLE_PREFIXES).items():
        vehicle_row = Bf6VehicleStats.model_validate({"id": item, **values})
        vehicle_row.kpm = _per_minute(vehicle_row.kills, vehicle_row.time_seconds)
        (vehicle_categories if item in _VEHICLE_CATEGORIES else vehicles).append(vehicle_row)

    kits = [
        Bf6KitStats.model_validate({"id": item, **values})
        for item, values in _group(stats, _KIT_PREFIXES).items()
    ]
    for kit in kits:
        kit.kd = ratio(kit.kills, kit.deaths)
    played_kits = [kit for kit in kits if kit.time_seconds]
    if played_kits:
        career.best_class = max(played_kits, key=lambda kit: kit.time_seconds or 0).id

    modes = [
        Bf6ModeStats.model_validate({"id": item, **values})
        for item, values in _group(stats, _MODE_PREFIXES).items()
        if item not in _MODE_AGGREGATES
    ]
    for mode in modes:
        mode.win_rate = ratio(mode.wins, mode.matches)

    maps = [
        Bf6MapStats.model_validate({"id": item, **values})
        for item, values in _group(stats, _MAP_PREFIXES).items()
        if item not in _MAP_AGGREGATES
    ]
    for map_row in maps:
        map_row.win_rate = ratio(map_row.wins, map_row.matches)

    return Bf6PlayerStats(
        nucleus_id=nucleus_id,
        has_data=bool(stats),
        career=career,
        weapons=_desc(weapons, "kills"),
        weapon_categories=_desc(weapon_categories, "kills"),
        vehicles=_desc(vehicles, "kills"),
        vehicle_categories=_desc(vehicle_categories, "kills"),
        kits=_desc(kits, "time_seconds"),
        modes=_desc(modes, "time_seconds"),
        maps=_desc(maps, "time_seconds"),
        fetched_at=fetched_at,
    )
