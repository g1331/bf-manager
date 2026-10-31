"""BF1 战绩查询服务"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.core.cache import get_cache
from app.domain.games.bf1 import round_awards
from app.domain.games.bf1.blaze_catalog import catalog, stat_names
from app.domain.games.bf1.blaze_stats import BlazeCareer
from app.domain.games.bf1.career_profile import BlazeProfile, parse_profile, profile_stat_names
from app.domain.games.bf1.maps import normalize_emblem_url, normalize_map_image_url
from app.domain.games.bf1.skins import SkinInfo, lookup_skin
from app.schemas.bf1.stats import (
    CareerCombat,
    CareerHonors,
    CareerMap,
    CareerMisc,
    CareerMode,
    CareerRibbon,
    CareerTeamwork,
    EliteKitStat,
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
from app.services.bf1.blaze_service import fetch_stats
from app.services.bf1.gateway_factory import get_bf1_client

logger = logging.getLogger(__name__)

# 战绩页的完整生涯一次要 7 个 Blaze 请求，同一个人 10 分钟内重复打开直接用缓存
CAREER_CACHE_KEY = "bf1:career:v2:{}"  # 字段有增减就换版本，免得读到缺字段的旧缓存
CAREER_CACHE_TTL = 600


def _build_summary(persona_id: int, career: BlazeCareer) -> PlayerStatsSummary:
    """从 Blaze 生涯数据组装综合战绩。纯函数，便于单测。"""
    spm = career.spm
    return PlayerStatsSummary(
        persona_id=persona_id,
        rank=career.rank or None,
        sps=spm / 60.0 if spm else None,
        kpm=career.kpm,
        kd=career.kd,
        wins=career.wins,
        losses=career.losses,
        time_played_seconds=round(career.seconds),
        kills=career.kills,
        deaths=career.deaths,
        skill=career.skill,
        infantry_kills=max(career.kills - career.vehicle_kills, 0),
        vehicle_kills=career.vehicle_kills,
        assists=career.assists or None,
        revives=career.revives or None,
        heals=career.heals or None,
        repairs=career.repairs or None,
        dogtags=career.dogtags or None,
        max_killstreak=career.max_killstreak or None,
        longest_headshot_meters=career.longest_headshot or None,
        best_class=career.best_kit,
    )


def _parse_online(res: Any, persona_id: int) -> OnlineStatus:
    """从 EA getServersByPersonaIds 返回判定在线状态。

    纯函数，便于单测。res.result 是 {str(pid): serverInfo | None} 的字典：该
    pid 的值为 dict 时在线（顺带取服务器名和 gameId），值为 null 时离线；result 不是
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
    if not isinstance(server, dict):
        return OnlineStatus(persona_id=persona_id, is_online=True)
    try:
        game_id = int(server["gameId"])
    except (KeyError, TypeError, ValueError):
        game_id = None
    return OnlineStatus(
        persona_id=persona_id, is_online=True, server_name=server.get("name"), game_id=game_id
    )


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


def _build_soldiers(career: BlazeCareer) -> list[SoldierClassStat]:
    """七个兵种的击杀 / 得分 / 在场时长，一次都没玩过的兵种不列"""
    return [
        SoldierClassStat(
            class_name=kit, kills=k.kills, score=k.score, time_seconds=round(k.seconds)
        )
        for kit, k in career.kits.items()
        if k.seconds or k.kills
    ]


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def _build_detail(persona_id: int, p: BlazeProfile, raw: dict[str, Any]) -> PlayerStatsDetail:
    """完整生涯 → 战绩页数据。纯函数，便于单测。"""
    c = p.career
    combat = CareerCombat(
        **p.combat,
        accuracy=_ratio(p.combat["hits"], p.combat["shots"]),
        headshot_rate=_ratio(p.combat["headshots"], c.kills),
    )
    return PlayerStatsDetail(
        summary=_build_summary(persona_id, c),
        soldiers=_build_soldiers(c),
        honors=CareerHonors(**p.honors),
        combat=combat,
        teamwork=CareerTeamwork(**p.teamwork),
        # 一局都没打过的模式不列
        modes=[
            CareerMode(
                mode=m.mode,
                wins=m.wins,
                losses=m.losses,
                win_rate=_ratio(m.wins, m.wins + m.losses),
                score=m.score,
            )
            for m in p.modes
            if m.wins or m.losses or m.score
        ],
        elite_kits=[
            EliteKitStat(kit=k.kit, kills=k.kills, time_seconds=round(k.seconds))
            for k in p.elite_kits
            if k.seconds or k.kills
        ],
        maps=sorted(
            (CareerMap(map=m, time_seconds=round(s)) for m, s in p.maps.items() if s >= 1),
            key=lambda m: -m.time_seconds,
        ),
        ribbons=None
        if p.ribbons is None
        else [
            CareerRibbon(code=round_awards.code(n), count=p.ribbons.get(n, 0))
            for n in round_awards.NUMBERS.values()
        ],
        misc=CareerMisc(
            rounds_completed=p.rounds_completed,
            rounds_played=p.rounds_played,
            completion_rate=_ratio(p.rounds_completed, p.rounds_played),
            spectator_seconds=round(p.spectator_seconds),
        ),
        raw=raw,
    )


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
# 分类名来自目录，加载时已转成简体
_VEHICLE_CATEGORY_TO_KIT: dict[str, str] = {"飞船": "24", "驱逐舰": "23"}


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
    """载具分类 → presets kit 编号；sortOrder 数值映射优先，飞船/驱逐舰按分类名"""
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


def _num(values: dict[str, float], stats: dict[str, str], field: str) -> float:
    name = stats.get(field)
    return values.get(name, 0.0) if name else 0.0


def _build_weapons(
    values: dict[str, float], skin_candidates: dict[str, list[str]]
) -> list[WeaponStat]:
    """按武器目录把 Blaze 统计组装成武器列表，用过的才列（无统计的配备总列），顺序沿用 Gateway；按 GUID 关联已装备皮肤"""
    weapons: list[WeaponStat] = []
    for entry in sorted(catalog("weapons").values(), key=lambda e: e["order"]):
        st = entry["stats"]
        kills, seconds = _num(values, st, "kills"), _num(values, st, "seconds")
        # 没有统计的配备（绷带包等）总是列出，与 Gateway 一致
        if st and not kills and not seconds:
            continue
        shots, hits = _num(values, st, "shots"), _num(values, st, "hits")
        guid = entry.get("guid")
        skin = _pick_skin(skin_candidates.get(guid.upper()) if guid else None)
        weapons.append(
            WeaponStat(
                name=entry["name"],
                category=entry["category"],
                kills=round(kills) or None,
                headshots=round(_num(values, st, "headshots")) or None,
                # 霰弹枪 / 投掷物一发多弹丸，命中率可以超过 100
                accuracy=(hits / shots * 100) if shots > 0 else None,
                time_seconds=seconds or None,
                # 武器贴图与地图图同为 [BB_PREFIX] 占位符，复用同一展开逻辑
                image=normalize_map_image_url(entry.get("image")),
                skin_name=skin["name"] if skin else None,
                skin_rarity=skin["rarity"] if skin else None,
                skin_image=skin["image"] if skin else None,
            )
        )
    return weapons


def _build_vehicles(
    values: dict[str, float], kit_candidates: dict[str, list[str]]
) -> list[VehicleStat]:
    """按载具目录组装载具列表。皮肤挂在 kit（分类）级，同分类多辆载具共享同一皮肤展示。"""
    vehicles: list[VehicleStat] = []
    for entry in sorted(catalog("vehicles").values(), key=lambda e: e["order"]):
        st = entry["stats"]
        kills, seconds = _num(values, st, "kills"), _num(values, st, "seconds")
        if not kills and not seconds:
            continue
        kit_number = _kit_number_for_category(entry.get("sort_order"), entry["category"])
        skin = _pick_skin(kit_candidates.get(kit_number)) if kit_number else None
        vehicles.append(
            VehicleStat(
                name=entry["name"],
                category=entry["category"],
                kills=round(kills) or None,
                destroyed=round(_num(values, st, "destroyed")) or None,
                time_seconds=seconds or None,
                image=normalize_map_image_url(entry.get("image")),
                skin_name=skin["name"] if skin else None,
                skin_rarity=skin["rarity"] if skin else None,
                skin_image=skin["image"] if skin else None,
            )
        )
    return vehicles


async def _fetch_presets_result(db: AsyncSession, persona_id: int) -> Any:
    """拉取玩家已装备皮肤映射（Gateway Loadout，Blaze 没有）；失败只降级皮肤展示（返回 None）。"""
    try:
        async with get_bf1_client(db) as client:
            res = await client.getPresetsByPersonaId(persona_id)
    except Exception as exc:
        logger.warning("BF1 presets 查询异常，皮肤展示降级 persona_id=%s: %s", persona_id, exc)
        return None
    if not isinstance(res, dict):
        logger.warning(
            "BF1 presets 查询失败，皮肤展示降级 persona_id=%s: %s", persona_id, str(res)[:128]
        )
        return None
    return res.get("result")


async def _fetch_one(
    db: AsyncSession, persona_id: int, names: dict[str, list[str]]
) -> dict[str, float]:
    values = await fetch_stats(db, [persona_id], names)
    if persona_id not in values:
        raise EAApiError(code="EA_STATS_FETCH_FAILED", message="Blaze 没有返回该玩家的生涯数据")
    return values[persona_id]


class BF1StatsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_detailed_stats(self, persona_id: int) -> PlayerStatsDetail:
        key = CAREER_CACHE_KEY.format(persona_id)
        cache = None
        hit = None
        try:
            cache = await get_cache()
            hit = await cache.get(key)
        except Exception as exc:
            logger.warning("BF1 生涯缓存读取失败 persona_id=%s: %s", persona_id, exc)
        if hit is not None:
            try:
                return PlayerStatsDetail.model_validate(hit)
            except Exception as exc:
                # 条目结构对不上（如 schema 改过）：当作没命中，查到后覆盖它
                logger.warning("BF1 生涯缓存条目无效 persona_id=%s: %s", persona_id, exc)
        values = await _fetch_one(self.db, persona_id, profile_stat_names())
        detail = _build_detail(persona_id, parse_profile(values), values)
        if cache is not None:
            try:
                await cache.set(key, detail.model_dump(mode="json"), ttl=CAREER_CACHE_TTL)
            except Exception as exc:
                logger.warning("BF1 生涯缓存写入失败 persona_id=%s: %s", persona_id, exc)
        return detail

    async def get_online_status(self, persona_id: int) -> OnlineStatus:
        async with get_bf1_client(self.db) as client:
            res = await client.getServersByPersonaIds([persona_id])
            return _parse_online(res, persona_id)

    async def get_platoon(self, persona_id: int) -> PlayerPlatoon | None:
        async with get_bf1_client(self.db) as client:
            res = await client.getActivePlatoon(persona_id)
            return _build_platoon(res)

    async def get_weapons(self, persona_id: int) -> WeaponStats:
        # Blaze 先查完再开 Gateway：两者共用 self.db，不并发
        values = await _fetch_one(self.db, persona_id, stat_names("weapons"))
        presets_result = await _fetch_presets_result(self.db, persona_id)
        return WeaponStats(
            persona_id=persona_id,
            weapons=_build_weapons(values, _extract_weapon_skin_candidates(presets_result)),
        )

    async def get_vehicles(self, persona_id: int) -> VehicleStats:
        values = await _fetch_one(self.db, persona_id, stat_names("vehicles"))
        presets_result = await _fetch_presets_result(self.db, persona_id)
        return VehicleStats(
            persona_id=persona_id,
            vehicles=_build_vehicles(values, _extract_kit_skin_candidates(presets_result)),
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
