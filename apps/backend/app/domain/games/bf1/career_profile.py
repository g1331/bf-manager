"""BF1 战绩页的完整生涯：career 之外的荣誉、战斗、团队、模式、精英兵、地图、勋带墙、杂项

只用于单人战绩页（一次 fetch_stats 读 core、statcategory 1/3/4 和 3 个勋带类别，共 7 个请求），
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

# 下面的统计名 2026-10-31 都用 Stats.getStatDescs 核对过存在（写错会让整个请求报错）
STAT3 = "player_statcategory3"
STAT4 = "player_statcategory4"

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
# 渗透者的击杀不在 statcategory，在 statcategory3
_ELITE_KILLS_IN_STAT3 = frozenset({"in"})
ROUNDS_COMPLETED, ROUNDS_PLAYED = "c___roo_g", "c___ro_g"
SPECTATOR_SECONDS = "c___sas_g"  # core

# 地图代号 → (类别, 在这张图上的秒数)。本体、庞然暗影、以沙皇之名、力挽狂澜、启示录的对应关系
# 写在统计描述里；誓死坚守的描述只有 XP1_001…006，对应关系取自 EA 勋章、小任务的条件
# （拉萨勒勋章「在凡尔登高地/法乌克斯要塞/苏瓦松/决裂进行击杀」用 xp1mp1…4，
# 小任务「坚守之处」的尼维尔之夜用 xp1mp5），mp6 是剩下的攻占托尔；2026-10-31 结算差值实测吻合。
# 空中优势（c_lmp10）和教学关（c_mptut）不算地图。
MAPS: dict[str, tuple[str, str]] = {
    "MP_Amiens": (STAT, "c_lmp1__so_g"),
    "MP_Chateau": (STAT, "c_lmp2__so_g"),
    "MP_Desert": (STAT, "c_lmp3__so_g"),
    "MP_FaoFortress": (STAT, "c_lmp4__so_g"),
    "MP_Forest": (STAT, "c_lmp5__so_g"),
    "MP_ItalianCoast": (STAT, "c_lmp6__so_g"),
    "MP_MountainFort": (STAT, "c_lmp7__so_g"),
    "MP_Scar": (STAT, "c_lmp8__so_g"),
    "MP_Suez": (STAT, "c_lmp9__so_g"),
    "MP_Giant": (STAT, "c_xp0g__so_g"),
    "MP_Verdun": (STAT, "c_xp1mp1__so_g"),
    "MP_Underworld": (STAT, "c_xp1mp2__so_g"),
    "MP_Fields": (STAT, "c_xp1mp3__so_g"),
    "MP_Graveyard": (STAT, "c_xp1mp4__so_g"),
    "MP_Trench": (STAT, "c_xp1mp5__so_g"),
    "MP_ShovelTown": (STAT, "c_xp1mp6__so_g"),
    "MP_Bridge": (STAT, "c_xp2mp1__so_g"),
    "MP_Ravines": (STAT, "c_xp2mp2__so_g"),
    "MP_Valley": (STAT, "c_xp2mp3__so_g"),
    "MP_Islands": (STAT, "c_xp2mp4__so_g"),
    "MP_Volga": (STAT, "c_xp2mp5__so_g"),
    "MP_Tsaritsyn": (STAT, "c_xp2mp6__so_g"),
    "MP_Beachhead": (STAT3, "c_xp3mp1__so_g"),
    "MP_Ridge": (STAT3, "c_xp3mp2__so_g"),
    "MP_Naval": (STAT3, "c_xp3mp3__so_g"),
    "MP_Harbor": (STAT3, "c_xp3mp4__so_g"),
    "MP_Hell": (STAT4, "c_xp4mp1__so_g"),
    "MP_Offensive": (STAT4, "c_xp4mp2__so_g"),
    "MP_River": (STAT4, "c_xp4mp3__so_g"),
    "MP_Blitz": (STAT4, "c_xp4mp4__so_g"),
    "MP_Alps": (STAT4, "c_xp4mp5__so_g"),
    "MP_London": (STAT4, "c_xp4mp6__so_g"),
}


class BlazeMode(BaseModel):
    mode: str
    wins: int = 0
    losses: int = 0
    score: int | None = None


class BlazeEliteKit(BaseModel):
    kit: str
    kills: int = 0
    seconds: float = 0.0


class BlazeProfile(BaseModel):
    """战绩页要的完整生涯：career 之外的荣誉、战斗、团队、模式、精英兵、地图、勋带墙、杂项"""

    career: BlazeCareer
    honors: dict[str, int]
    combat: dict[str, int]
    teamwork: dict[str, int]
    modes: list[BlazeMode]
    elite_kits: list[BlazeEliteKit]
    # 地图代号 → 在这张图上的秒数
    maps: dict[str, float]
    # 勋带号 → 次数；None 表示勋带类别没返回这个人
    ribbons: dict[int, int] | None
    rounds_completed: int = 0
    rounds_played: int = 0
    spectator_seconds: float = 0.0


def profile_stat_names() -> dict[str, list[str]]:
    """战绩页一次查询的全部统计：career_stat_names 加上面几组、statcategory3/4 和 3 个勋带类别"""
    names = career_stat_names() | {STAT3: [], STAT4: []}
    names[STAT] += [*HONORS.values(), *COMBAT.values(), *TEAMWORK.values()]
    names[STAT] += [f"c_m{r}_{code}_roo_g" for code, _ in MODES.values() for r in ("win", "los")]
    names[CORE] += [score for _, score in MODES.values() if score]
    for k in ELITE_KITS.values():
        names[STAT3 if k in _ELITE_KILLS_IN_STAT3 else STAT].append(f"c_{k}__ks_g")
    names[CORE] += [f"c_{k}__sa_g" for k in ELITE_KITS.values()]
    names[STAT] += [ROUNDS_COMPLETED, ROUNDS_PLAYED]
    names[CORE].append(SPECTATOR_SECONDS)
    for cat, name in MAPS.values():
        names[cat].append(name)
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
                kills=n(f"c_{k}__ks_g"),
                seconds=values.get(f"c_{k}__sa_g", 0.0),
            )
            for kit, k in ELITE_KITS.items()
        ],
        maps={m: values.get(name, 0.0) for m, (_, name) in MAPS.items()},
        ribbons=round_awards.read(values),
        rounds_completed=n(ROUNDS_COMPLETED),
        rounds_played=n(ROUNDS_PLAYED),
        spectator_seconds=values.get(SPECTATOR_SECONDS, 0.0),
    )
