"""BF1 单局战绩：生涯差分用到的统计字典与紧凑编码

EA 只在两个时刻把战绩写进生涯：回合结算时整服一起写，玩家中途退出时立刻写这个人的（不加局数和
胜负）。所以一个人「结算或退出后的生涯 − 进服时的生涯」就是他这一局的战绩。2026-10-27 用 5 台
满人服实测：每次结算 52–63 人同时局数 +1，一队全胜、一队全负，退出的人在下一次查询里就能看到增量。

单局增量绝大多数是 0，只存非零项：每项写成两个 varint（与上一项编号的间隔, 增量值），小于 128 的
数占 1 字节，一局通常十几项、三四十字节。编号即 ROUND_STATS 里的下标，**只能往后追加**，改顺序会
让已存的数据解错。核心项后面依次接：

- 武器载具的增量（见 round_weapons），编号 WEAPON_BASE + 槽位；
- 勋带的增量（见 round_awards），编号 AWARD_BASE + 勋带号；
- 本局拿到服役星的武器载具，编号 STAR_BASE + 条目下标，值是新的星数。

有没有读到武器载具、勋带分别记在队伍状态字节的 WITH_WEAPONS、WITH_AWARDS 位上，没有这一位的条目
（功能上线前的、读失败的）不能当成「没用武器」「没拿勋带」。

多数核心项是「终值 − 基线」，有两类例外（2026-10-31 实测）：最高连杀、最远爆头这类生涯最大值和
等级减不出单局数值，记的是「变大了的新值」（END_VALUE）；技巧值一局有升有降，记有符号的增量
（SIGNED，zigzag 编码），保留一位小数（SCALE）。
"""

from __future__ import annotations

from typing import NamedTuple

from app.domain.games.bf1.blaze_stats import CORE, ELITE_SECONDS, KITS, STAT

# 兵种升级勋章的代号 → 兵种：c_awkr<代号>__ga_g
KIT_RANK_AWARDS: dict[str, str] = {
    "a": "assault",
    "m": "medic",
    "su": "support",
    "sc": "scout",
    "vp": "pilot",
    "vc": "cavalry",
    "vt": "tanker",
}

# (类别, 统计名)，除 END_VALUE、SIGNED 外都是只增不减的累计值；统计名都已在生产核对过
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
    # —— 2026-10-31 追加：荣誉、得分构成、目标、团队、战斗、成长、纪录 ——
    (STAT, "c_fip__psx_g"),  # MVP：每次结算正好 1 人
    (STAT, "c___bc_g"),  # 王牌小队：每次结算正好 5 人
    (STAT, "c_aA__ga_g"),  # 获得勋带数，也是读勋带类别的门控
    (STAT, "c_mA__ga_g"),  # 获得勋章数
    (CORE, "sc_general"),  # 得分构成：常规
    (CORE, "sc_team"),  # 团队
    (CORE, "sc_squad"),  # 小队
    (CORE, "sc_bonus"),  # 结算奖励：只在打到结算时给，不进游戏内计分板
    (CORE, "sc_award"),  # 勋带勋章奖励：经验，不进游戏内计分板
    (CORE, "sc_rank"),  # 本局经验
    (CORE, "sc_conquest"),  # 各模式的目标得分，一局只有一项非零
    (CORE, "sc_operations"),
    (CORE, "sc_rush"),
    (CORE, "sc_possession"),
    (CORE, "sc_tugofwar"),
    (CORE, "sc_domination"),
    (CORE, "sc_deathmatch"),
    (STAT, "c___ccp_g"),  # 占点
    (STAT, "c___cpd_g"),  # 守点
    (STAT, "c___ca_g"),  # 突袭：安放炸弹
    (STAT, "c___cdi_g"),  # 突袭：拆除炸弹
    (STAT, "c___kw_g"),  # 突袭：火炮防守击杀
    (STAT, "c_Possd__m_g"),  # 战争信鸽：送出信鸽
    (STAT, "c_Possw__m_g"),  # 战争信鸽：写信
    (STAT, "c_Possk__m_g"),  # 战争信鸽：击杀信鸽兵
    (STAT, "c___rs_g"),  # 补给
    (STAT, "c___sp_g"),  # 索敌助攻
    (STAT, "c___sua_g"),  # 压制助攻
    (STAT, "c___ss_g"),  # 小队重生
    (STAT, "c___orc_g"),  # 完成命令
    (STAT, "c___skak_g"),  # 小队击杀助攻
    (STAT, "c___hsh_g"),  # 爆头
    (STAT, "c___sfw_g"),  # 开火
    (STAT, "c___shw_g"),  # 命中
    (STAT, "c___sd_g"),  # 对步兵伤害
    (STAT, "c___vd_g"),  # 对载具伤害
    (STAT, "c___ak_g"),  # 复仇击杀
    (STAT, "c___sk_g"),  # 救星击杀
    (STAT, "c___nx_g"),  # 宿敌击杀
    (STAT, "c___sqw_g"),  # 团灭
    (STAT, "c_av__de_g"),  # 摧毁载具
    *((STAT, f"c_awkr{k}__ga_g") for k in KIT_RANK_AWARDS),  # 兵种升级
    (STAT, "c_awkr__ga_g"),  # 兵种升级合计
    (CORE, "rank"),  # 等级（终值）
    (CORE, "skill"),  # 技巧值（有符号增量）
    (STAT, "c___k_ghvs"),  # 最高连杀（终值）
    (STAT, "c___hsd_ghva"),  # 最远爆头，米（终值）
    (STAT, "c___nk_ghva"),  # 最高宿敌连杀（终值）
]

KILLS, DEATHS, WINS, LOSSES, ROUNDS, SCORE = range(6)
ASSISTS, REVIVES, HEALS, REPAIRS, DOGTAGS, VEHICLE_KILLS = range(6, 12)
KIT_BASE = 12  # 每个兵种依次是 击杀、得分、在场秒数
ELITE = KIT_BASE + 3 * len(KITS)

_AT = {name: i for i, (_, name) in enumerate(ROUND_STATS)}
MVP, ACE_SQUAD, RIBBONS, MEDALS = (
    _AT[n] for n in ("c_fip__psx_g", "c___bc_g", "c_aA__ga_g", "c_mA__ga_g")
)
SC_BONUS, SC_AWARD = _AT["sc_bonus"], _AT["sc_award"]
# 得分构成，键即接口字段名；模式得分合成一项 objective
SCORE_PARTS: dict[str, int] = {
    "general": _AT["sc_general"],
    "team": _AT["sc_team"],
    "squad": _AT["sc_squad"],
    "award": SC_AWARD,
    "bonus": SC_BONUS,
    "xp": _AT["sc_rank"],
}
MODE_SCORES = tuple(
    _AT[n]
    for n in (
        "sc_conquest",
        "sc_operations",
        "sc_rush",
        "sc_possession",
        "sc_tugofwar",
        "sc_domination",
        "sc_deathmatch",
    )
)
OBJECTIVE: dict[str, int] = {
    "flag_captures": _AT["c___ccp_g"],
    "flag_defends": _AT["c___cpd_g"],
    "bombs_placed": _AT["c___ca_g"],
    "bombs_defused": _AT["c___cdi_g"],
    "artillery_defense_kills": _AT["c___kw_g"],
    "pigeons_delivered": _AT["c_Possd__m_g"],
    "pigeons_written": _AT["c_Possw__m_g"],
    "pigeon_carriers_killed": _AT["c_Possk__m_g"],
    "resupplies": _AT["c___rs_g"],
    "spot_assists": _AT["c___sp_g"],
    "suppression_assists": _AT["c___sua_g"],
    "squad_spawns": _AT["c___ss_g"],
    "orders_completed": _AT["c___orc_g"],
    "squad_kill_assists": _AT["c___skak_g"],
}
COMBAT: dict[str, int] = {
    "headshots": _AT["c___hsh_g"],
    "shots": _AT["c___sfw_g"],
    "hits": _AT["c___shw_g"],
    "soldier_damage": _AT["c___sd_g"],
    "vehicle_damage": _AT["c___vd_g"],
    "avenger_kills": _AT["c___ak_g"],
    "savior_kills": _AT["c___sk_g"],
    "nemesis_kills": _AT["c___nx_g"],
    "squad_wipes": _AT["c___sqw_g"],
    "vehicles_destroyed": _AT["c_av__de_g"],
}
KIT_RANKS: dict[str, int] = {kit: _AT[f"c_awkr{k}__ga_g"] for k, kit in KIT_RANK_AWARDS.items()}
RANK, SKILL = _AT["rank"], _AT["skill"]
RECORDS: dict[str, int] = {
    "max_killstreak": _AT["c___k_ghvs"],
    "longest_headshot": _AT["c___hsd_ghva"],
    "max_nemesis_streak": _AT["c___nk_ghva"],
}
# 存终值：变大了才记新值，没变记 0
END_VALUE = frozenset({RANK, *RECORDS.values()})
# 有正负的增量，zigzag 编码，不参与负数校验
SIGNED = frozenset({SKILL})
# 读进来先乘这个倍数再取整（技巧值带两位小数，一局变化在 ±40 以内，留一位）
SCALE: dict[int, int] = {SKILL: 10}

# 一个人在这一局的状态：打完结算了、中途退出、增量里混了别的局（局数 +2 等），不可信
FINISHED, LEFT_EARLY, SUSPECT = range(3)

# 条目里各段的编号起点：核心项 < 武器载具槽位 < 勋带号 < 服役星（条目下标），各段只能往后追加到
# 下一段之前。武器槽位 = 条目下标 × 6 + 指标，现有约 1800，到 AWARD_BASE 还能再加近千个条目
WEAPON_BASE = 1024
AWARD_BASE = 8192
STAR_BASE = AWARD_BASE + 256
# 队伍状态字节里「这一条带武器载具数据」「这一条带勋带数据」的位
WITH_WEAPONS = 1 << 4
WITH_AWARDS = 1 << 5

# 结算探测只看完成局数，一个统计名的请求最轻
PROBE_NAMES: dict[str, list[str]] = {STAT: ["c___roo_g"]}
# 进服后复查只看局数和胜负（迟到的结算只改这几项），都在同一个类别里，一个请求就够
RECHECK_FIELDS = (ROUNDS, WINS, LOSSES)
RECHECK_NAMES: dict[str, list[str]] = {STAT: [ROUND_STATS[i][1] for i in RECHECK_FIELDS]}


def round_stat_names() -> dict[str, list[str]]:
    """{类别: 统计名}，喂给 Stats.getStats"""
    names: dict[str, list[str]] = {}
    for cat, name in ROUND_STATS:
        names.setdefault(cat, []).append(name)
    return names


def to_vector(values: dict[str, float]) -> list[int]:
    """Blaze 返回的 {统计名: 数值} → 按 ROUND_STATS 排好的整数向量，缺的按 0。秒数、助攻带小数，取整。"""
    return [
        round(values.get(name, 0.0) * SCALE.get(i, 1)) for i, (_, name) in enumerate(ROUND_STATS)
    ]


def diff(end: list[int], base: list[int]) -> list[int] | None:
    """这一局的增量；累计值不该变小，出现负数说明数据不对（换号、回档），返回 None。

    END_VALUE 项给变大后的新值，SIGNED 项可正可负。base 比 end 短（追加统计项前查到的基线、
    跨部署接着跟的局）时，基线里没有的项按 0 记。
    """
    out = [0] * len(end)
    for i, (a, b) in enumerate(zip(end, base, strict=False)):
        if i in END_VALUE:
            out[i] = a if a > b else 0
        elif (d := a - b) < 0 and i not in SIGNED:
            return None
        else:
            out[i] = d
    return out


def same_core(a: list[int], b: list[int]) -> bool:
    """两份核心向量的共有部分相同；长度不同是因为其中一份查于追加统计项之前。"""
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def write_varint(out: bytearray, v: int) -> None:
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    v = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        v |= (b & 0x7F) << shift
        if b < 0x80:
            return v, pos
        shift += 7


def _zigzag(v: int) -> int:
    return v << 1 if v >= 0 else (-v << 1) - 1


def _unzigzag(v: int) -> int:
    return v >> 1 if not v & 1 else -((v + 1) >> 1)


class Entry(NamedTuple):
    """一个人一局的条目"""

    round_id: int
    team: int
    status: int
    stats: dict[int, int]  # {统计编号: 增量}，只有非零项
    weapons: dict[int, int] | None  # {武器载具槽位: 增量}；None 表示没读到
    awards: dict[int, int] | None  # {勋带号: 次数}；None 表示没读到
    stars: dict[int, int]  # {武器载具条目下标: 新的星数}


def encode_entry(
    round_id: int,
    team: int,
    status: int,
    delta: list[int],
    weapons: dict[int, int] | None = None,
    awards: dict[int, int] | None = None,
    stars: dict[int, int] | None = None,
) -> bytes:
    """一个人一局：round_id、(队伍 | 状态 << 2 | 标志位)、非零项个数，再跟非零项。条目首尾相接追加存放。

    weapons / awards 是武器载具槽位、勋带号的非零增量；None 表示没读到（与「读到了、全是 0」的
    空 dict 区分）。stars 只在有武器载具数据时才有。
    """
    out = bytearray()
    write_varint(out, round_id)
    flags = (WITH_WEAPONS if weapons is not None else 0) | (
        WITH_AWARDS if awards is not None else 0
    )
    write_varint(out, team | status << 2 | flags)
    nonzero = [(i, _zigzag(v) if i in SIGNED else v) for i, v in enumerate(delta) if v]
    for base, extra in ((WEAPON_BASE, weapons), (AWARD_BASE, awards), (STAR_BASE, stars)):
        nonzero += [(base + k, v) for k, v in sorted((extra or {}).items()) if v]
    write_varint(out, len(nonzero))
    prev = 0
    for i, v in nonzero:
        write_varint(out, i - prev)
        write_varint(out, v)
        prev = i
    return bytes(out)


def decode_entries(buf: bytes) -> list[Entry]:
    out = []
    pos = 0
    while pos < len(buf):
        round_id, pos = read_varint(buf, pos)
        packed, pos = read_varint(buf, pos)
        n, pos = read_varint(buf, pos)
        stats: dict[int, int] = {}
        weapons: dict[int, int] | None = {} if packed & WITH_WEAPONS else None
        awards: dict[int, int] | None = {} if packed & WITH_AWARDS else None
        stars: dict[int, int] = {}
        idx = 0
        for _ in range(n):
            gap, pos = read_varint(buf, pos)
            idx += gap
            v, pos = read_varint(buf, pos)
            if idx >= STAR_BASE:
                stars[idx - STAR_BASE] = v
            elif idx >= AWARD_BASE and awards is not None:
                awards[idx - AWARD_BASE] = v
            elif idx >= WEAPON_BASE and weapons is not None:
                weapons[idx - WEAPON_BASE] = v
            else:
                stats[idx] = _unzigzag(v) if idx in SIGNED else v
        out.append(
            Entry(round_id, packed & 0b11, packed >> 2 & 0b11, stats, weapons, awards, stars)
        )
    return out


def pack_pids(pids: list[int]) -> bytes:
    """pid 排序后存差值：personaId 有 10–13 位，差值能省下一半左右。"""
    out = bytearray()
    prev = 0
    for pid in sorted(set(pids)):
        write_varint(out, pid - prev)
        prev = pid
    return bytes(out)


def unpack_pids(buf: bytes) -> list[int]:
    out, pos, prev = [], 0, 0
    while pos < len(buf):
        d, pos = read_varint(buf, pos)
        prev += d
        out.append(prev)
    return out


def pack_vector(vec: list[int]) -> bytes:
    """整条生涯向量（全是非负整数）逐项 varint，存快照用。"""
    out = bytearray()
    for v in vec:
        write_varint(out, v)
    return bytes(out)


def unpack_vector(buf: bytes) -> list[int]:
    out, pos = [], 0
    while pos < len(buf):
        v, pos = read_varint(buf, pos)
        out.append(v)
    return out
