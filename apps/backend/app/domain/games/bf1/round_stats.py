"""BF1 单局战绩：生涯差分用到的统计字典与紧凑编码

EA 只在两个时刻把战绩写进生涯：回合结算时整服一起写，玩家中途退出时立刻写这个人的（不加局数和
胜负）。所以一个人「结算或退出后的生涯 − 进服时的生涯」就是他这一局的战绩。2026-10-27 用 5 台
满人服实测：每次结算 52–63 人同时局数 +1，一队全胜、一队全负，退出的人在下一次查询里就能看到增量。

单局增量绝大多数是 0，只存非零项：每项写成两个 varint（与上一项编号的间隔, 增量值），小于 128 的
数占 1 字节，一局通常十几项、三四十字节。编号即 ROUND_STATS 里的下标，**只能往后追加**，改顺序会
让已存的数据解错。
"""

from __future__ import annotations

from app.domain.games.bf1.blaze_stats import CORE, ELITE_SECONDS, KITS, STAT

# (类别, 统计名)，都是只增不减的累计值；同一请求里的统计名都已在生产核对过
ROUND_STATS: list[tuple[str, str]] = [
    (STAT, "kills"),
    (STAT, "c___d_g"),  # 死亡
    (STAT, "c_mwin__roo_g"),  # 胜局
    (STAT, "c_mlos__roo_g"),  # 败局
    (STAT, "c___roo_g"),  # 完成局数：结算 +1，中途退出不加
    (CORE, "score"),
    (STAT, "c___kak_g"),  # 助攻
    (STAT, "c___re_g"),  # 复活
    (STAT, "c___h_g"),  # 治疗
    (STAT, "c___r_g"),  # 修理
    (STAT, "c___dt_g"),  # 狗牌
    (STAT, "c_av__ki_g"),  # 载具击杀
    *(
        stat
        for kit, k in KITS.items()
        for stat in ((STAT, f"c_{k}__ks_g"), (CORE, f"sc_{kit}"), (CORE, f"c_{k}__sa_g"))
    ),
    (CORE, ELITE_SECONDS),  # 精英兵在场秒数
]

KILLS, DEATHS, WINS, LOSSES, ROUNDS, SCORE = range(6)
ASSISTS, REVIVES, HEALS, REPAIRS, DOGTAGS, VEHICLE_KILLS = range(6, 12)
KIT_BASE = 12  # 每个兵种依次是 击杀、得分、在场秒数
ELITE = KIT_BASE + 3 * len(KITS)

# 一个人在这一局的状态：打完结算了、中途退出、增量里混了别的局（局数 +2 等），不可信
FINISHED, LEFT_EARLY, SUSPECT = range(3)

# 结算探测只看完成局数，一个统计名的请求最轻
PROBE_NAMES: dict[str, list[str]] = {STAT: ["c___roo_g"]}


def round_stat_names() -> dict[str, list[str]]:
    """{类别: 统计名}，喂给 Stats.getStats"""
    names: dict[str, list[str]] = {}
    for cat, name in ROUND_STATS:
        names.setdefault(cat, []).append(name)
    return names


def to_vector(values: dict[str, float]) -> list[int]:
    """Blaze 返回的 {统计名: 数值} → 按 ROUND_STATS 排好的整数向量，缺的按 0。秒数、助攻带小数，取整。"""
    return [round(values.get(name, 0.0)) for _, name in ROUND_STATS]


def diff(end: list[int], base: list[int]) -> list[int] | None:
    """end − base；累计值不该变小，出现负数说明数据不对（换号、回档），返回 None。"""
    out = [a - b for a, b in zip(end, base, strict=True)]
    return None if any(v < 0 for v in out) else out


def _put(out: bytearray, v: int) -> None:
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)


def _get(buf: bytes, pos: int) -> tuple[int, int]:
    v = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        v |= (b & 0x7F) << shift
        if b < 0x80:
            return v, pos
        shift += 7


def encode_entry(round_id: int, team: int, status: int, delta: list[int]) -> bytes:
    """一个人一局：round_id、(队伍 | 状态 << 2)、非零项个数，再跟非零项。条目首尾相接追加存放。"""
    out = bytearray()
    _put(out, round_id)
    _put(out, team | status << 2)
    nonzero = [(i, v) for i, v in enumerate(delta) if v]
    _put(out, len(nonzero))
    prev = 0
    for i, v in nonzero:
        _put(out, i - prev)
        _put(out, v)
        prev = i
    return bytes(out)


def decode_entries(buf: bytes) -> list[tuple[int, int, int, dict[int, int]]]:
    """→ [(round_id, 队伍, 状态, {统计编号: 增量})]"""
    out = []
    pos = 0
    while pos < len(buf):
        round_id, pos = _get(buf, pos)
        packed, pos = _get(buf, pos)
        n, pos = _get(buf, pos)
        stats: dict[int, int] = {}
        idx = 0
        for _ in range(n):
            gap, pos = _get(buf, pos)
            idx += gap
            stats[idx], pos = _get(buf, pos)
        out.append((round_id, packed & 0b11, packed >> 2, stats))
    return out


def pack_pids(pids: list[int]) -> bytes:
    """pid 排序后存差值：personaId 有 10–13 位，差值能省下一半左右。"""
    out = bytearray()
    prev = 0
    for pid in sorted(set(pids)):
        _put(out, pid - prev)
        prev = pid
    return bytes(out)


def unpack_pids(buf: bytes) -> list[int]:
    out, pos, prev = [], 0, 0
    while pos < len(buf):
        d, pos = _get(buf, pos)
        prev += d
        out.append(prev)
    return out
