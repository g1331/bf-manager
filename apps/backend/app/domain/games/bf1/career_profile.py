"""BF1 战绩页的完整生涯：career 之外的荣誉、战斗、团队、模式、精英兵、勋带墙、杂项

只用于单人战绩页（一次 fetch_stats 读 core、statcategory 和 3 个勋带类别，共 5 个请求），
不进计分板的批量查询（那边只要 blaze_stats.career_stat_names）。
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.games.bf1 import round_awards
from app.domain.games.bf1.blaze_stats import (
    CORE,
    STAT,
    BlazeCareer,
    career_stat_names,
    parse_career,
)

# 下面的统计名 2026-10-31 都用 Stats.getStatDescs 核对过存在（写错会让整个请求报错）；
# 渗透者击杀、勋带总数在 player_statcategory3，还没核对，先不读

HONORS: dict[str, str] = {
    "mvp": "c_fip__psx_g",
    "ace_squad": "c___bc_g",
    "ribbons": "c_aA__ga_g",
    "medals": "c_mA__ga_g",
}
COMBAT: dict[str, str] = {
    "headshots": "c___hsh_g",
    "shots": "c___sfw_g",
    "hits": "c___shw_g",
    "avenger_kills": "c___ak_g",
    "savior_kills": "c___sk_g",
    "nemesis_kills": "c___nx_g",
    "max_nemesis_streak": "c___nk_ghva",
    "squad_wipes": "c___sqw_g",
    "vehicles_destroyed": "c_av__de_g",
}
TEAMWORK: dict[str, str] = {
    "resupplies": "c___rs_g",
    "spot_assists": "c___sp_g",
    "suppression_assists": "c___sua_g",
    "squad_spawns": "c___ss_g",
    "orders_completed": "c___orc_g",
    "squad_kill_assists": "c___skak_g",
    "flag_captures": "c___ccp_g",
    "flag_defends": "c___cpd_g",
}
# 模式 → (胜负统计里的模式代号, 模式目标得分)；空中突袭没有
MODES: dict[str, tuple[str, str | None]] = {
    "conquest": ("mgc", "sc_conquest"),
    "operations": ("mgb", "sc_operations"),
    "rush": ("mgr", "sc_rush"),
    "frontlines": ("mgf", "sc_tugofwar"),
    "domination": ("mgdo", "sc_domination"),
    "war_pigeons": ("Poss", "sc_possession"),
    "team_deathmatch": ("mgtd", "sc_deathmatch"),
    "air_assault": ("mgaas", None),
}
# 精英兵 → 缩写：击杀 c_<k>__ks_g（statcategory）、在场秒数 c_<k>__sa_g（core）
ELITE_KITS: dict[str, str] = {
    "sentry": "st",
    "flamethrower": "fl",
    "trench_raider": "tr",
    "tank_hunter": "at",
    "infiltrator": "in",
}
# 渗透者的击杀在 statcategory3，还没核对
_ELITE_NO_KILLS = frozenset({"in"})
ROUNDS_COMPLETED, ROUNDS_PLAYED = "c___roo_g", "c___ro_g"
SPECTATOR_SECONDS = "c___sas_g"  # core


class BlazeMode(BaseModel):
    mode: str
    wins: int = 0
    losses: int = 0
    score: int | None = None


class BlazeEliteKit(BaseModel):
    kit: str
    kills: int | None = None  # None：这项还没读
    seconds: float = 0.0


class BlazeProfile(BaseModel):
    """战绩页要的完整生涯：career 之外的荣誉、战斗、团队、模式、精英兵、勋带墙、杂项"""

    career: BlazeCareer
    honors: dict[str, int]
    combat: dict[str, int]
    teamwork: dict[str, int]
    modes: list[BlazeMode]
    elite_kits: list[BlazeEliteKit]
    # 勋带号 → 次数；None 表示勋带类别没返回这个人
    ribbons: dict[int, int] | None
    rounds_completed: int = 0
    rounds_played: int = 0
    spectator_seconds: float = 0.0


def profile_stat_names() -> dict[str, list[str]]:
    """战绩页一次查询的全部统计：career_stat_names 加上面几组和 3 个勋带类别"""
    names = career_stat_names()
    names[STAT] += [*HONORS.values(), *COMBAT.values(), *TEAMWORK.values()]
    names[STAT] += [f"c_m{r}_{code}_roo_g" for code, _ in MODES.values() for r in ("win", "los")]
    names[CORE] += [score for _, score in MODES.values() if score]
    names[STAT] += [f"c_{k}__ks_g" for k in ELITE_KITS.values() if k not in _ELITE_NO_KILLS]
    names[CORE] += [f"c_{k}__sa_g" for k in ELITE_KITS.values()]
    names[STAT] += [ROUNDS_COMPLETED, ROUNDS_PLAYED]
    names[CORE].append(SPECTATOR_SECONDS)
    return names | round_awards.names()


def parse_profile(values: dict[str, float]) -> BlazeProfile:
    def n(name: str) -> int:
        return round(values.get(name, 0.0))

    return BlazeProfile(
        career=parse_career(values),
        honors={k: n(v) for k, v in HONORS.items()},
        combat={k: n(v) for k, v in COMBAT.items()},
        teamwork={k: n(v) for k, v in TEAMWORK.items()},
        modes=[
            BlazeMode(
                mode=mode,
                wins=n(f"c_mwin_{code}_roo_g"),
                losses=n(f"c_mlos_{code}_roo_g"),
                score=n(score) if score else None,
            )
            for mode, (code, score) in MODES.items()
        ],
        elite_kits=[
            BlazeEliteKit(
                kit=kit,
                kills=None if k in _ELITE_NO_KILLS else n(f"c_{k}__ks_g"),
                seconds=values.get(f"c_{k}__sa_g", 0.0),
            )
            for kit, k in ELITE_KITS.items()
        ],
        ribbons=round_awards.read(values),
        rounds_completed=n(ROUNDS_COMPLETED),
        rounds_played=n(ROUNDS_PLAYED),
        spectator_seconds=values.get(SPECTATOR_SECONDS, 0.0),
    )
