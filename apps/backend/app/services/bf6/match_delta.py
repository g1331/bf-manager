"""两次生涯快照（global 维度 {统计名: 值}）之间的增量，整理成一条对局估算。

做法和统计名口径见 ``stats_normalizer``：模式、地图、武器、载具、兵种都按统计名前缀拆。
EA 不返回值为 0 的统计行，缺的行按 0 算。
"""

from __future__ import annotations

from app.schemas.bf6.matches import Bf6MatchDelta, Bf6MatchItem, Bf6MatchSplit
from app.services.bf6.stats_normalizer import (
    MAP_AGGREGATES,
    MODE_AGGREGATES,
    VEHICLE_CATEGORIES,
    WEAPON_CATEGORIES,
    WEAPON_CATEGORY_ALIASES,
    WEAPON_TOTAL,
    ratio,
)

# 场次和战斗时间是判断“打过对局”的依据，也用来识别 EA 那边的数据回退
_MATCHES = "matches_gm_all"
_TIME = "tp_kit"
_MONOTONIC = (_MATCHES, _TIME, "score_total")

_WEAPON_SKIP = WEAPON_CATEGORIES | set(WEAPON_CATEGORY_ALIASES) | {WEAPON_TOTAL}
_TOP_WEAPONS = 3
_TOP_VEHICLES = 2


def _ids(stats: dict[str, int], prefix: str, skip: set[str] | frozenset[str]) -> set[str]:
    return {
        name[len(prefix) :]
        for name in stats
        if name.startswith(prefix) and name[len(prefix) :] and name[len(prefix) :] not in skip
    }


def diff(prev: dict[str, int], cur: dict[str, int]) -> Bf6MatchDelta | None:
    """场次和战斗时间都没涨时返回 None；EA 的累计值变小了（数据回退）也返回 None，调用方直接换成新快照。"""
    if any(cur.get(key, 0) < prev.get(key, 0) for key in _MONOTONIC):
        return None

    def d(name: str) -> int:
        return max(cur.get(name, 0) - prev.get(name, 0), 0)

    matches, time_seconds = d(_MATCHES), d(_TIME)
    if not matches and not time_seconds:
        return None

    def splits(prefix: str, skip: set[str]) -> list[Bf6MatchSplit]:
        rows = [
            Bf6MatchSplit(
                id=item,
                matches=d(f"matches_{prefix}{item}"),
                wins=d(f"wins_{prefix}{item}"),
                losses=d(f"losses_{prefix}{item}"),
            )
            for item in _ids(cur, f"matches_{prefix}", skip)
        ]
        return sorted((r for r in rows if r.matches), key=lambda r: (-r.matches, r.id))

    def items(
        kills_prefix: str, time_prefix: str, skip: set[str], limit: int
    ) -> list[Bf6MatchItem]:
        ids = _ids(cur, kills_prefix, skip) | _ids(cur, time_prefix, skip)
        rows = [
            Bf6MatchItem(
                id=item,
                kills=d(kills_prefix + item),
                time_seconds=d(time_prefix + item),
            )
            for item in ids
        ]
        played = (r for r in rows if r.kills or r.time_seconds)
        return sorted(played, key=lambda r: (-r.kills, -r.time_seconds, r.id))[:limit]

    kit_times = {item: d(f"tp_kit_{item}") for item in _ids(cur, "tp_kit_", set())}
    kit = max(kit_times, key=lambda k: (kit_times[k], k)) if any(kit_times.values()) else None

    human_kills, deaths = d("human_kills_total"), d("deaths_total")
    return Bf6MatchDelta(
        matches=matches,
        wins=d("wins_gm_all"),
        losses=d("losses_gm_all"),
        modes=splits("gm_", MODE_AGGREGATES),
        maps=splits("lvl", MAP_AGGREGATES),
        kills=d("Kills_Total"),
        human_kills=human_kills,
        deaths=deaths,
        score=d("score_total"),
        time_seconds=time_seconds,
        damage=d("Dmg_Dealt_Total"),
        assists=d("Assist_Total"),
        revives=d("Revives_Teammates_Total"),
        headshots=d("kills_Headshots_Total"),
        xp=d("xp_all"),
        kit=kit,
        weapons=items("kw_wp_", "tp_wp_", _WEAPON_SKIP, _TOP_WEAPONS),
        vehicles=items("kw_veh_", "tp_veh_", VEHICLE_CATEGORIES, _TOP_VEHICLES),
        # 一条命没丢时 K/D 没有意义，留空让前端显示击杀数
        kd=ratio(human_kills, deaths, 2),
        kpm=ratio(human_kills, time_seconds / 60 if time_seconds else None, 2),
    )
