"""BF1 单局武器载具：生涯差分用到的统计槽位、哨兵与快照编码

和核心战绩一样靠生涯差分：一局的武器载具数据 = 终值 − 基线。条目来自 blaze_catalog（每把枪有击杀、
秒数、爆头、命中、开火，载具和迫击炮有击杀、秒数、摧毁），分散在 7 个类别：

- player_statcategory 里的 40 种载具和迫击炮，跟核心战绩同一个请求，顺带读；
- player_weapons1–5，有武器变化的人每次都要读；
- player_statcategory3（驱逐舰、飞船、SK45 岸防炮）和 player_statcategory4（两架轰炸机）用的人
  很少（2026-10-28 实测轰炸机 4–5% 的行、另三种一小时没人用），先看哨兵：STAT / 核心里覆盖它们的
  合计没变，就沿用上次的值，不读。轰炸机的哨兵「Planes - Bombers」已实测对得上（26/26）；
  驱逐舰、飞船没有现成合计，用海上、空中、巨兽载具得分和固定武器合计兜着，跟踪器按比例抽查兜底。

槽位编号 = 条目在 data/round_items.json 里的下标 × 6 + 指标下标。那份列表**只能往后追加**，改顺序
会让已存的数据解错；目录重新生成后有新条目，追加到末尾即可。

快照（某一时刻一个人全部条目的生涯值加哨兵值）编码成 bytes：哨兵个数、各哨兵值，再跟非零槽位的
(与上一槽的间隔, 值)，都是 varint。一个人约 1.4 KB（160 人样本中位数，p90 2.5 KB）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.domain.games.bf1.blaze_catalog import catalog
from app.domain.games.bf1.blaze_stats import CORE, STAT
from app.domain.games.bf1.round_stats import read_varint, round_stat_names, write_varint

METRICS = ("kills", "seconds", "headshots", "hits", "shots", "destroyed")
KILLS_METRIC = METRICS.index("kills")

# 读武器时每次都读的类别；STAT 里的条目随核心查询一起读
ALWAYS = (
    "player_weapons1",
    "player_weapons2",
    "player_weapons3",
    "player_weapons4",
    "player_weapons5",
)
# 有哨兵的冷门类别 → 覆盖它的合计；合计都在 STAT / 核心里，随核心查询一起读
GATES: dict[str, tuple[tuple[str, str], ...]] = {
    "player_statcategory3": (
        (STAT, "c_sw__si_g"),  # Stationary Weapons 秒数、击杀、摧毁：含 SK45
        (STAT, "c_sw__ki_g"),
        (STAT, "c__sw_di_g"),
        (CORE, "sc_seavehicles"),  # 驱逐舰
        (CORE, "sc_airvehicles"),  # 飞船
        (CORE, "sc_behvehicles"),
    ),
    "player_statcategory4": (
        (STAT, "c_plBo__si_g"),  # Planes - Bombers：含两架轰炸机
        (STAT, "c_plBo__ki_g"),
        (STAT, "c__plBo_di_g"),
    ),
}
GATE_NAMES: list[tuple[str, str]] = [g for gs in GATES.values() for g in gs]


def _gate_slices() -> dict[str, slice]:
    out, start = {}, 0
    for cat, gs in GATES.items():
        out[cat] = slice(start, start + len(gs))
        start += len(gs)
    return out


# 每个冷门类别的哨兵在快照哨兵列表里的区间
GATE_SLICES = _gate_slices()

_ITEMS_PATH = Path(__file__).parent / "data" / "round_items.json"


@lru_cache(maxsize=1)
def items() -> list[str]:
    """槽位列表里的条目键（w:代号 / v:代号），下标 × 6 + 指标下标即槽位"""
    with _ITEMS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def slots() -> dict[int, tuple[str, str]]:
    """{槽位: (类别, 统计名)}；目录里找不到的条目（目录重新生成时删掉的）跳过，槽位照旧占着。"""
    kinds = {"w": catalog("weapons"), "v": catalog("vehicles")}
    out: dict[int, tuple[str, str]] = {}
    for i, key in enumerate(items()):
        kind, code = key.split(":", 1)
        entry = kinds[kind].get(code)
        if not entry or not entry["stats"]:
            continue
        for metric, name in entry["stats"].items():
            out[i * len(METRICS) + METRICS.index(metric)] = (entry["cat"], name)
    return out


@lru_cache(maxsize=1)
def slots_by_category() -> dict[str, dict[int, str]]:
    """{类别: {槽位: 统计名}}"""
    out: dict[str, dict[int, str]] = {}
    for slot, (cat, name) in slots().items():
        out.setdefault(cat, {})[slot] = name
    return out


def slot_item(slot: int) -> tuple[str, str]:
    """槽位 → (条目键如 w:wSPMaxim, 指标)"""
    return items()[slot // len(METRICS)], METRICS[slot % len(METRICS)]


def core_extra_names() -> dict[str, list[str]]:
    """读武器载具时，核心查询要顺带读的统计名：STAT 里的条目和全部哨兵。"""
    names: dict[str, list[str]] = {STAT: list(slots_by_category().get(STAT, {}).values())}
    for cat, name in GATE_NAMES:
        names.setdefault(cat, []).append(name)
    return names


def category_names(cat: str) -> dict[str, list[str]]:
    return {cat: list(slots_by_category()[cat].values())}


def read_slots(values: dict[str, float], cat: str) -> dict[int, int] | None:
    """Blaze 返回的 {统计名: 数值} 里这个类别的非零槽位；一项都没有说明这一类没返回，给 None。"""
    names = slots_by_category()[cat]
    if not any(name in values for name in names.values()):
        return None
    return {slot: v for slot, name in names.items() if (v := round(values.get(name, 0.0)))}


def read_gates(values: dict[str, float]) -> list[int]:
    return [round(values.get(name, 0.0)) for _, name in GATE_NAMES]


def pack(gates: list[int], values: dict[int, int]) -> bytes:
    out = bytearray()
    write_varint(out, len(gates))
    for v in gates:
        write_varint(out, v)
    prev = 0
    for slot in sorted(values):
        if values[slot]:
            write_varint(out, slot - prev)
            write_varint(out, values[slot])
            prev = slot
    return bytes(out)


def unpack(buf: bytes) -> tuple[list[int], dict[int, int]]:
    n, pos = read_varint(buf, 0)
    gates = []
    for _ in range(n):
        v, pos = read_varint(buf, pos)
        gates.append(v)
    values: dict[int, int] = {}
    slot = 0
    while pos < len(buf):
        gap, pos = read_varint(buf, pos)
        slot += gap
        values[slot], pos = read_varint(buf, pos)
    return gates, values


def in_category(values: dict[int, int], cat: str) -> dict[int, int]:
    names = slots_by_category().get(cat, {})
    return {slot: v for slot, v in values.items() if slot in names}


def diff(end: bytes, base: bytes) -> dict[int, int] | None:
    """两份快照的非零增量；出现负数说明数据不对，返回 None。"""
    _, e = unpack(end)
    _, b = unpack(base)
    out: dict[int, int] = {}
    for slot in e.keys() | b.keys():
        d = e.get(slot, 0) - b.get(slot, 0)
        if d < 0:
            return None
        if d:
            out[slot] = d
    return out


def kills(delta: dict[int, int]) -> int:
    """各武器载具击杀之和，用来和核心击杀对账。"""
    return sum(v for slot, v in delta.items() if slot % len(METRICS) == KILLS_METRIC)


def full_names() -> dict[str, list[str]]:
    """读武器载具时核心查询的统计名：核心战绩加上顺带读的条目和哨兵。"""
    names = round_stat_names()
    for cat, extra in core_extra_names().items():
        have = names.setdefault(cat, [])
        have += [n for n in extra if n not in have]
    return names
