"""BF1 Blaze 生涯统计：统计名映射与数据模型

Blaze ``Stats.getStats`` 按「类别 + 统计名」批量取数，一次最多 64 人，返回的全是数字串。这里
把 Gateway ``detailedStatsByPersonaId`` 用到的生涯字段映射到 Blaze 统计名（2026-10 用 40 名玩家
两边逐字段对照，数值一致），整理成 ``BlazeCareer``。

与 Gateway 的口径差异：Gateway 的 timePlayed 在 Blaze 里没有完全相同的统计，这里用 8 个兵种
（含精英兵）在场秒数之和，偏差在 1% 以内；spm / kpm 都按这个时长算。载具击杀用 Blaze 的
All Vehicles（含船只与巨兽），Gateway 只算空中、装甲、运输、马匹、固定武器五组。
"""

from __future__ import annotations

from pydantic import BaseModel

CORE = "player_core"
STAT = "player_statcategory"

# 字段 → (类别, 统计名)
CAREER_STATS: dict[str, tuple[str, str]] = {
    "kills": (STAT, "kills"),
    "deaths": (STAT, "c___d_g"),
    "wins": (STAT, "c_mwin__roo_g"),
    "losses": (STAT, "c_mlos__roo_g"),
    "assists": (STAT, "c___kak_g"),
    "revives": (STAT, "c___re_g"),
    "heals": (STAT, "c___h_g"),
    "repairs": (STAT, "c___r_g"),
    "dogtags": (STAT, "c___dt_g"),
    "max_killstreak": (STAT, "c___k_ghvs"),
    "longest_headshot": (STAT, "c___hsd_ghva"),
    "vehicle_kills": (STAT, "c_av__ki_g"),
    "score": (CORE, "score"),
    "rank": (CORE, "rank"),
    "skill": (CORE, "skill"),
}

# 兵种代号 → Blaze 缩写：击杀 c_<k>__ks_g、在场秒数 c_<k>__sa_g、得分 sc_<兵种>
KITS: dict[str, str] = {
    "assault": "as",
    "medic": "md",
    "support": "sp",
    "scout": "sc",
    "tanker": "tk",
    "pilot": "pt",
    "cavalry": "cv",
}
# 精英兵（哨兵、火焰兵等）只计入总时长，Gateway 的兵种分布里也没有它
ELITE_SECONDS = "c_kfk__sa_g"


class BlazeKitStats(BaseModel):
    kills: int = 0
    score: int = 0
    seconds: float = 0.0


class BlazeCareer(BaseModel):
    kills: int = 0
    deaths: int = 0
    wins: int = 0
    losses: int = 0
    assists: int = 0
    revives: int = 0
    heals: int = 0
    repairs: int = 0
    dogtags: int = 0
    max_killstreak: int = 0
    longest_headshot: float = 0.0
    vehicle_kills: int = 0
    score: int = 0
    rank: int = 0
    skill: float = 0.0
    seconds: float = 0.0  # 游玩时长：各兵种在场秒数之和
    kits: dict[str, BlazeKitStats] = {}

    @property
    def kd(self) -> float | None:
        return self.kills / self.deaths if self.deaths else None

    @property
    def kpm(self) -> float | None:
        return self.kills / self.seconds * 60 if self.seconds else None

    @property
    def spm(self) -> float | None:
        return self.score / self.seconds * 60 if self.seconds else None

    @property
    def win_rate(self) -> float | None:
        """百分比 0-100"""
        rounds = self.wins + self.losses
        return self.wins / rounds * 100 if rounds else None

    @property
    def best_kit(self) -> str | None:
        """在场时间最长的兵种，与 Gateway favoriteClass 一致（40 人对照全部吻合）"""
        best = max(self.kits.items(), key=lambda kv: kv[1].seconds, default=None)
        return best[0] if best and best[1].seconds > 0 else None


def career_stat_names() -> dict[str, list[str]]:
    """{类别: 统计名}，喂给 Stats.getStats"""
    names: dict[str, list[str]] = {CORE: [ELITE_SECONDS], STAT: []}
    for cat, name in CAREER_STATS.values():
        names[cat].append(name)
    for kit, k in KITS.items():
        names[STAT].append(f"c_{k}__ks_g")
        names[CORE] += [f"c_{k}__sa_g", f"sc_{kit}"]
    return names


def parse_career(values: dict[str, float]) -> BlazeCareer:
    """values 为 {统计名: 数值}（各类别合并），缺失的统计按 0 处理"""
    fields: dict[str, float | int] = {}
    for field, (_, name) in CAREER_STATS.items():
        v = values.get(name, 0.0)
        # Blaze 全按 %.2f 下发，int 字段带小数时 pydantic 会拒收
        fields[field] = round(v) if BlazeCareer.model_fields[field].annotation is int else v
    kits = {
        kit: BlazeKitStats(
            kills=round(values.get(f"c_{k}__ks_g", 0)),
            score=round(values.get(f"sc_{kit}", 0)),
            seconds=values.get(f"c_{k}__sa_g", 0.0),
        )
        for kit, k in KITS.items()
    }
    seconds = sum(k.seconds for k in kits.values()) + values.get(ELITE_SECONDS, 0.0)
    return BlazeCareer.model_validate({**fields, "seconds": seconds, "kits": kits})
