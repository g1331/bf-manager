"""BF1 单局勋带：统计名、门控与快照编码

47 种勋带各有一个生涯次数 ``rNN_00``（编号与图鉴 ribbons.json 的 code 一致），分在 3 个类别里，
要单独读。和武器载具一样靠生涯差分，单局次数 = 终值 − 基线，同一勋带一局可以拿好几次。

2026-10-31 实测：勋带与击杀、得分同一轮写入，中途退出也立即写；核心里的「获得勋带数」
c_aA__ga_g 与勋带次数之和基本一致（157 次里 144 次严格相等，其余是分两轮写入），勋章阶段完成
另加 sc_award。所以这两项都没变就沿用上次的勋带值，不读这 3 个类别；跟踪器按比例抽查兜底。

快照编码复用 round_weapons.pack：门控值，再跟非零勋带的 (与上一号的间隔, 次数)。
"""

from __future__ import annotations

from app.domain.games.bf1.round_stats import RIBBONS, SC_AWARD

# 类别 → 勋带号（2026-10-31 用 Stats.getStatDescs 核对）
CATEGORIES: dict[str, range] = {
    "player_awards": range(1, 40),
    "player_awards3": range(40, 46),
    "player_awards4": range(46, 48),
}
NUMBERS: dict[str, int] = {f"r{n:02d}_00": n for ns in CATEGORIES.values() for n in ns}
# 门控：核心向量里的这几项都没变，勋带就没变
GATES = (RIBBONS, SC_AWARD)


def names() -> dict[str, list[str]]:
    """{类别: 统计名}，3 个类别放在一次 fetch 里"""
    return {cat: [f"r{n:02d}_00" for n in ns] for cat, ns in CATEGORIES.items()}


def gates(vec: list[int]) -> list[int]:
    return [vec[i] for i in GATES]


def read(values: dict[str, float]) -> dict[int, int] | None:
    """Blaze 返回的 {统计名: 数值} 里的非零勋带次数 {勋带号: 次数}。

    3 个类别是分开请求再按人合并的，有一类没返回这个人（一个名字都不在）就给 None，
    不能把缺的计数当成 0：存成快照后，下一次差分会出负数，或把历史次数算进以后的对局。
    """
    for ns in CATEGORIES.values():
        if not any(f"r{n:02d}_00" in values for n in ns):
            return None
    return {n: v for name, n in NUMBERS.items() if (v := round(values.get(name, 0.0)))}


def code(number: int) -> str:
    """勋带号 → 图鉴 code（r01…r47）"""
    return f"r{number:02d}"
