"""BF1 战绩查询服务"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.domain.games.bf1.maps import normalize_emblem_url, normalize_map_image_url
from app.domain.games.bf1.skins import SkinInfo, lookup_skin
from app.schemas.bf1.stats import (
    OnlineStatus,
    PlayerPlatoon,
    PlayerStatsDetail,
    PlayerStatsSummary,
    RecentServer,
    RecentServers,
    SoldierClassStat,
    VehicleStat,
    VehicleStats,
    WeaponStat,
    WeaponStats,
)
from app.services.bf1.gateway_factory import get_bf1_client

logger = logging.getLogger(__name__)


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


def _build_summary(persona_id: int, raw: dict[str, Any]) -> PlayerStatsSummary:
    """从 EA detailedStats 的 result 字典提取生涯综合战绩。

    纯函数，不触发任何网络/数据库，便于单测。字段归属：基础值与技巧值在
    basicStats；战斗细分项（协助/复活/治疗/修理/狗牌/连杀/最远爆头）在 result
    顶层；载具击杀按 vehicleStats[].killsAs 求和、步战击杀为总击杀减载具击杀；
    最佳兵种取顶层 favoriteClass（英文代号转小写）。
    """
    basic = raw.get("basicStats", {}) or {}
    kills = int(_safe(basic.get("kills"), 0))
    deaths = int(_safe(basic.get("deaths"), 0))
    wins = int(_safe(basic.get("wins"), 0))
    losses = int(_safe(basic.get("losses"), 0))
    time_played = int(_safe(basic.get("timePlayed"), 0))
    spm = basic.get("spm")
    ea_rank = int(_safe(basic.get("rank"), 0)) or None
    rank = ea_rank if ea_rank else _calc_rank_from_exp(spm, time_played)
    vehicle_stats = raw.get("vehicleStats") or []
    vehicle_kills = sum(int(_safe(v.get("killsAs"), 0)) for v in vehicle_stats)
    infantry_kills = max(kills - vehicle_kills, 0)
    longest_headshot = raw.get("longestHeadShot")
    favorite_class = raw.get("favoriteClass")
    return PlayerStatsSummary(
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
        skill=float(basic["skill"]) if basic.get("skill") is not None else None,
        # vehicleStats 缺失时步战/载具击杀无法可靠拆分，统一留空而非填 0 误导
        infantry_kills=infantry_kills if vehicle_stats else None,
        vehicle_kills=vehicle_kills if vehicle_stats else None,
        assists=int(_safe(raw.get("killAssists"), 0)) or None,
        revives=int(_safe(raw.get("revives"), 0)) or None,
        heals=int(_safe(raw.get("heals"), 0)) or None,
        repairs=int(_safe(raw.get("repairs"), 0)) or None,
        dogtags=int(_safe(raw.get("dogtagsTaken"), 0)) or None,
        max_killstreak=int(_safe(raw.get("highestKillStreak"), 0)) or None,
        longest_headshot_meters=float(longest_headshot) if longest_headshot is not None else None,
        best_class=favorite_class.lower()
        if isinstance(favorite_class, str) and favorite_class
        else None,
    )


def _parse_online(res: Any, persona_id: int) -> OnlineStatus:
    """从 EA getServersByPersonaIds 返回判定在线状态。

    纯函数，便于单测。res.result 是 {str(pid): serverInfo | None} 的字典：该
    pid 的值为 dict 时在线（顺带取服务器名），值为 null 时离线；result 不是
    字典、或该 pid 缺席、或整体返回结构异常时无法判定，is_online 置 None。
    """
    if not isinstance(res, dict):
        return OnlineStatus(persona_id=persona_id, is_online=None)
    result = res.get("result")
    if not isinstance(result, dict) or str(persona_id) not in result:
        return OnlineStatus(persona_id=persona_id, is_online=None)
    server = result.get(str(persona_id))
    if server is None:
        return OnlineStatus(persona_id=persona_id, is_online=False)
    server_name = server.get("name") if isinstance(server, dict) else None
    return OnlineStatus(persona_id=persona_id, is_online=True, server_name=server_name)


def _build_platoon(res: Any) -> PlayerPlatoon | None:
    """从 EA Platoons.getActivePlatoon 返回提取玩家当前战队。

    纯函数，便于单测。res.result 为 dict 时玩家有战队（含 guid/name/tag/size/
    description/emblem/verified），为 null 时玩家无战队、返回 None；整体返回结构
    异常（非 dict、result 非 dict）同样返回 None。emblem 占位符展开为可加载 URL。
    """
    if not isinstance(res, dict):
        return None
    result = res.get("result")
    if not isinstance(result, dict):
        return None
    size_raw = result.get("size")
    try:
        size = int(size_raw) if size_raw is not None else None
    except (TypeError, ValueError):
        size = None
    return PlayerPlatoon(
        guid=result.get("guid"),
        tag=result.get("tag"),
        name=result.get("name"),
        size=size,
        description=result.get("description"),
        emblem_url=normalize_emblem_url(result.get("emblem")),
        verified=bool(result.get("verified")),
    )


def _build_soldiers(raw: dict[str, Any]) -> list[SoldierClassStat]:
    """从 EA detailedStats 的 result.kitStats 提取各兵种击杀分布。

    kitStats 每项含 name（英文兵种代号）/kills/score/secondsAs，兵种代号转小写
    与前端对齐。kitStats 缺失或为空时返回空列表。
    """
    soldiers: list[SoldierClassStat] = []
    for kit in raw.get("kitStats") or []:
        name = kit.get("name")
        if not isinstance(name, str) or not name:
            continue
        soldiers.append(
            SoldierClassStat(
                class_name=name.lower(),
                kills=int(_safe(kit.get("kills"), 0)),
                score=int(_safe(kit.get("score"), 0)),
                time_seconds=int(_safe(kit.get("secondsAs"), 0)),
            )
        )
    return soldiers


# 载具皮肤在 Loadout presets 中按 kit 编号存放，分类级 sortOrder → kit 编号映射
# （部署机实测：sortOrder 在分类级而非载具级）。飛船 / 驅逐艦 的 sortOrder 同为 14
# 无法用数值区分，按分类名匹配。未列出的分类（攻擊機 / 戰鬥機 / 地面載具 / 船隻 /
# 定點武器 / 機械巨獸 / 馬匹）没有已知 kit 编号，不展示皮肤。
_VEHICLE_SORT_ORDER_TO_KIT: dict[int, str] = {
    5: "17",  # 重型坦克
    4: "12",  # 巡航坦克
    6: "14",  # 輕型坦克
    7: "15",  # 火砲裝甲車
    8: "20",  # 攻擊坦克
    9: "22",  # 突擊裝甲車
    1: "16",  # 轟炸機
    2: "21",  # 重型轟炸機
}
_VEHICLE_CATEGORY_TO_KIT: dict[str, str] = {"飛船": "24", "驅逐艦": "23"}


def _slot_sorted_guids(slots: Any) -> list[str]:
    """把 preset 槽位映射 {槽位号: guid} 按槽位号升序展开为 guid 列表。

    上游槽位键是数字字符串且无序，排序保证取值确定；形态异常返回空列表。
    """
    if not isinstance(slots, dict):
        return []
    entries = [
        (key, value)
        for key, value in slots.items()
        if isinstance(key, str) and isinstance(value, str) and value
    ]
    entries.sort(key=lambda item: int(item[0]) if item[0].isdigit() else len(item[0]))
    return [value for _, value in entries]


def _extract_weapon_skin_candidates(presets_result: Any) -> dict[str, list[str]]:
    """从 Loadout presets 的 result.weapons 提取 {武器 GUID(大写): 候选皮肤 guid 列表}。

    槽位中混有非皮肤物件的 guid，调用方经 _pick_skin 取第一个在皮肤表命中的。
    结构异常（result 非 dict、weapons 缺失等）一律返回空映射，降级为无皮肤。
    """
    if not isinstance(presets_result, dict):
        return {}
    weapons = presets_result.get("weapons")
    if not isinstance(weapons, dict):
        return {}
    candidates: dict[str, list[str]] = {}
    for guid, slots in weapons.items():
        guids = _slot_sorted_guids(slots)
        if isinstance(guid, str) and guids:
            candidates[guid.upper()] = guids
    return candidates


def _extract_kit_skin_candidates(presets_result: Any) -> dict[str, list[str]]:
    """从 Loadout presets 的 result.kits 提取 {kit 编号: 候选皮肤 guid 列表}。

    kits 值是 preset 列表（实测单元素），取第一个 preset 的槽位映射。
    """
    if not isinstance(presets_result, dict):
        return {}
    kits = presets_result.get("kits")
    if not isinstance(kits, dict):
        return {}
    candidates: dict[str, list[str]] = {}
    for kit_number, presets in kits.items():
        slots = presets[0] if isinstance(presets, list) and presets else None
        guids = _slot_sorted_guids(slots)
        if isinstance(kit_number, str) and guids:
            candidates[kit_number] = guids
    return candidates


def _kit_number_for_category(sort_order: Any, name: str | None) -> str | None:
    """载具分类 → presets kit 编号；sortOrder 数值映射优先，飛船/驅逐艦按分类名"""
    if isinstance(sort_order, int) and sort_order in _VEHICLE_SORT_ORDER_TO_KIT:
        return _VEHICLE_SORT_ORDER_TO_KIT[sort_order]
    if name is not None and name in _VEHICLE_CATEGORY_TO_KIT:
        return _VEHICLE_CATEGORY_TO_KIT[name]
    return None


def _pick_skin(candidates: list[str] | None) -> SkinInfo | None:
    """取候选 guid 中第一个在皮肤表命中的；全部未命中（均为非皮肤物件）返回 None"""
    for guid in candidates or []:
        skin = lookup_skin(guid)
        if skin is not None:
            return skin
    return None


def _build_weapons(raw: Any, skin_candidates: dict[str, list[str]]) -> list[WeaponStat]:
    """从 EA getWeaponsByPersonaId 的 result 构造武器列表，按武器 GUID 关联已装备皮肤"""
    weapons: list[WeaponStat] = []
    for category in raw or []:
        cat_name = category.get("name") or category.get("category")
        for w in category.get("weapons") or []:
            stats = w.get("stats", {}).get("values", {}) or {}
            hits = float(_safe(stats.get("hits"), 0))
            shots = float(_safe(stats.get("shots"), 0))
            # EA 上游会把 accuracy 截到 100；霰弹枪 / 投掷物的多弹丸命中应当 > 100，
            # 因此用 hits/shots 自己算，绕开 EA 端的截断。
            accuracy = (hits / shots * 100) if shots > 0 else None
            guid = w.get("guid")
            skin = _pick_skin(skin_candidates.get(guid.upper()) if isinstance(guid, str) else None)
            weapons.append(
                WeaponStat(
                    name=w.get("name"),
                    category=cat_name,
                    kills=int(_safe(stats.get("kills"), 0)) or None,
                    headshots=int(_safe(stats.get("headshots"), 0)) or None,
                    accuracy=accuracy,
                    time_seconds=float(_safe(stats.get("seconds"), 0)) or None,
                    # 武器贴图与地图图同为 [BB_PREFIX] 占位符，复用同一展开逻辑，
                    # 否则前端拿到的是无法直接加载的占位串。
                    image=normalize_map_image_url(w.get("imageUrl")),
                    skin_name=skin["name"] if skin else None,
                    skin_rarity=skin["rarity"] if skin else None,
                    skin_image=skin["image"] if skin else None,
                )
            )
    return weapons


def _build_vehicles(raw: Any, kit_candidates: dict[str, list[str]]) -> list[VehicleStat]:
    """从 EA getVehiclesByPersonaId 的 result 构造载具列表。

    皮肤挂在 kit（分类）级而非单辆载具上，同分类多辆载具共享同一皮肤展示。
    """
    vehicles: list[VehicleStat] = []
    for category in raw or []:
        cat_name = category.get("name") or category.get("category")
        kit_number = _kit_number_for_category(category.get("sortOrder"), cat_name)
        skin = _pick_skin(kit_candidates.get(kit_number)) if kit_number else None
        for v in category.get("vehicles") or []:
            stats = v.get("stats", {}).get("values", {}) or {}
            vehicles.append(
                VehicleStat(
                    name=v.get("name"),
                    category=cat_name,
                    kills=int(_safe(stats.get("kills"), 0)) or None,
                    destroyed=int(_safe(stats.get("destroyed"), 0)) or None,
                    time_seconds=float(_safe(stats.get("seconds"), 0)) or None,
                    image=normalize_map_image_url(v.get("imageUrl")),
                    skin_name=skin["name"] if skin else None,
                    skin_rarity=skin["rarity"] if skin else None,
                    skin_image=skin["image"] if skin else None,
                )
            )
    return vehicles


async def _fetch_presets_result(client: BF1GatewayClient, persona_id: int) -> Any:
    """拉取玩家已装备皮肤映射；失败只降级皮肤展示（返回 None），不影响主数据。

    与主查询串行而非 gather 并行：gateway 的 session 过期重登无锁，且刷新回调
    会写共享的 AsyncSession，并发调用存在竞态窗口。
    """
    res = await client.getPresetsByPersonaId(persona_id)
    if not isinstance(res, dict):
        logger.warning(
            "BF1 presets 查询失败，皮肤展示降级 persona_id=%s: %s", persona_id, str(res)[:128]
        )
        return None
    return res.get("result")


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
            return PlayerStatsDetail(
                summary=_build_summary(persona_id, raw),
                soldiers=_build_soldiers(raw),
                raw=raw,
            )

    async def get_online_status(self, persona_id: int) -> OnlineStatus:
        async with get_bf1_client(self.db) as client:
            res = await client.getServersByPersonaIds([persona_id])
            return _parse_online(res, persona_id)

    async def get_platoon(self, persona_id: int) -> PlayerPlatoon | None:
        async with get_bf1_client(self.db) as client:
            res = await client.getActivePlatoon(persona_id)
            return _build_platoon(res)

    async def get_weapons(self, persona_id: int) -> WeaponStats:
        async with get_bf1_client(self.db) as client:
            res = await client.getWeaponsByPersonaId(persona_id)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_WEAPONS_FETCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            presets_result = await _fetch_presets_result(client, persona_id)
        return WeaponStats(
            persona_id=persona_id,
            weapons=_build_weapons(
                res.get("result") or [],
                _extract_weapon_skin_candidates(presets_result),
            ),
        )

    async def get_vehicles(self, persona_id: int) -> VehicleStats:
        async with get_bf1_client(self.db) as client:
            res = await client.getVehiclesByPersonaId(persona_id)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_VEHICLES_FETCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            presets_result = await _fetch_presets_result(client, persona_id)
        return VehicleStats(
            persona_id=persona_id,
            vehicles=_build_vehicles(
                res.get("result") or [],
                _extract_kit_skin_candidates(presets_result),
            ),
        )

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
