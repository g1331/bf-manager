"""BF1 服务器浏览器的玩法开关目录与掩码判读。

开关清单、顺序、默认值与简体名取自游戏自己的 ``Gamedata.getGameData``（data/gamedata.zh-CN.json
的 settings.Misc / Weapons / Vehicles / Kits），名称与详情页的设置展示一致。Blaze 快照 ATTR 里
每组开关压成一个整数掩码，位序经部署机对照官服与私服实测：

- vehiclemask：bit0 地面载具 L，bit1 空中载具 A
- weaponmask：bit0..9 依次为 M S H E LMG SMG SAR SR KG SIR
- kitmask：bit0..3 为兵种 1..4，bit9 为精英兵种 HERO
- settingmask：bit0..20 与 Misc 清单同序
- scalemask：每项倍率按选项一位、恰好一位为 1，从低位起依次是兵力值 TC1..3（bit0..2）、
  重生时间 SR1..3（bit3..5）、载具重置时间 VR1..3（bit6..8）、子弹伤害 BD1..4（bit9..12）、
  回合时限 RT1..5（bit13..17）。默认 9362 即 TC2 SR2 VR2 BD2 RT1

开关与倍率统称「规则」，键形如 ``vehicles.L`` / ``scales.BD``，取值分别是 on/off 与选项键（BD3）。
同一套规则也能写进 EA searchServers 的 filterJson：开关组里列出的 key 设 on 即要求开、off 即
要求关，没列出的不约束；scales 组列出的选项都必须满足（同一项列两个档位会返回 0 台），
所以倍率按单选处理。各组之间取交集。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# 开关的取值是 on / off，倍率的取值是选项键（BD3），统一按字符串处理
RuleValue = str


@dataclass(frozen=True)
class SettingToggle:
    group: str  # 本站分组名，也是规则前缀
    key: str  # 游戏 filterKey
    label: str
    bit: int
    default: bool

    @property
    def rule_key(self) -> str:
        return f"{self.group}.{self.key}"


@dataclass(frozen=True)
class SettingGroup:
    id: str
    label: str
    ea_key: str  # filterJson 里的组名
    mask_field: str  # ServerMasks 上对应的字段
    toggles: tuple[SettingToggle, ...]


def _group(
    gid: str, label: str, ea_key: str, mask_field: str, rows: list[tuple[str, str, int, bool]]
) -> SettingGroup:
    toggles = tuple(SettingToggle(gid, k, lbl, bit, d) for k, lbl, bit, d in rows)
    return SettingGroup(gid, label, ea_key, mask_field, toggles)


SETTING_GROUPS: tuple[SettingGroup, ...] = (
    _group(
        "vehicles",
        "载具",
        "vehicles",
        "vehicle",
        [("L", "地面载具", 0, True), ("A", "空中载具", 1, True)],
    ),
    _group(
        "kits",
        "兵种",
        "kits",
        "kit",
        [
            ("1", "突击兵", 0, True),
            ("2", "医护兵", 1, True),
            ("3", "支援兵", 2, True),
            ("4", "侦察兵", 3, True),
            ("HERO", "精英兵种", 9, True),
        ],
    ),
    _group(
        "weapons",
        "武器",
        "weaponClasses",
        "weapon",
        [
            ("M", "近战武器", 0, True),
            ("S", "霰弹枪", 1, True),
            ("H", "手枪", 2, True),
            ("E", "爆裂物", 3, True),
            ("LMG", "轻机枪", 4, True),
            ("SMG", "冲锋枪", 5, True),
            ("SAR", "半自动步枪", 6, True),
            ("SR", "单动式步枪", 7, True),
            ("KG", "兵种配备", 8, True),
            ("SIR", "制式步枪", 9, False),
        ],
    ),
    _group(
        "misc",
        "进阶",
        "misc",
        "setting",
        [
            ("KC", "击杀镜头", 0, True),
            ("MM", "抬头显示", 1, True),
            ("FF", "友军炮火", 2, False),
            ("RH", "自动回复生命值", 3, True),
            ("3S", "3D 索敌", 4, True),
            ("MS", "迷你地图标记", 5, True),
            ("F", "永久迷雾", 6, False),
            ("NT", "名牌", 7, True),
            ("3VC", "载具第三人称视角", 8, True),
            ("SLSO", "只能在小队长附近重生", 9, False),
            ("BH", "机械巨兽", 10, True),
            ("RWM", "加载填满弹匣", 11, False),
            ("MV", "地图投票", 12, True),
            ("BPL", "禁用回合前就绪阶段", 13, False),
            ("AAR", "瞄准辅助自动转向", 14, True),
            ("AAS", "瞄准辅助减速", 15, True),
            ("LL", "延迟锁定", 16, False),
            ("LNL", "允许较高延迟", 17, False),
            ("UM", "无上限弹匣", 18, False),
            ("DSD", "禁用观众延迟", 19, False),
            ("DTB", "禁用队伍平衡", 20, False),
        ],
    ),
)

TOGGLES: dict[str, SettingToggle] = {t.rule_key: t for g in SETTING_GROUPS for t in g.toggles}
GROUPS: dict[str, SettingGroup] = {g.id: g for g in SETTING_GROUPS}


@dataclass(frozen=True)
class ScaleOption:
    key: str  # 游戏选项键，例如 BD3
    value: float
    bit: int


@dataclass(frozen=True)
class ScaleSetting:
    key: str  # 选项键前缀，例如 BD
    name: str  # gamedata 里的 filterKey，例如 BulletDamage
    label: str
    default: str
    options: tuple[ScaleOption, ...]  # 按倍率从小到大

    @property
    def rule_key(self) -> str:
        return f"scales.{self.key}"


def _scale(
    key: str, name: str, label: str, default: str, offset: int, values: list[float]
) -> ScaleSetting:
    opts = [ScaleOption(f"{key}{i + 1}", v, offset + i) for i, v in enumerate(values)]
    return ScaleSetting(key, name, label, default, tuple(sorted(opts, key=lambda o: o.value)))


# 顺序同游戏设置界面
SCALE_SETTINGS: tuple[ScaleSetting, ...] = (
    _scale("BD", "BulletDamage", "子弹伤害", "BD2", 9, [0.5, 1.0, 2.0, 1.25]),
    _scale("TC", "TicketCount", "兵力值", "TC2", 0, [0.5, 1.0, 2.0]),
    _scale("SR", "SoldierRespawnTime", "重生时间", "SR2", 3, [0.5, 1.0, 2.0]),
    _scale("VR", "VehicleRespawnTime", "载具重置时间", "VR2", 6, [0.5, 1.0, 2.0]),
    _scale("RT", "RoundTimeLimit", "回合时限", "RT1", 13, [0.0, 0.5, 1.0, 2.0, 5.0]),
)
SCALES: dict[str, ScaleSetting] = {s.rule_key: s for s in SCALE_SETTINGS}

# 规则键 → 允许的取值
RULE_VALUES: dict[str, frozenset[str]] = {
    **{key: frozenset({"on", "off"}) for key in TOGGLES},
    **{key: frozenset(o.key for o in s.options) for key, s in SCALES.items()},
}


@dataclass(frozen=True)
class SettingPreset:
    id: str
    label: str
    rules: dict[str, RuleValue]


PRESETS: tuple[SettingPreset, ...] = (
    SettingPreset(
        "vanilla",
        "原版设置",
        {
            **{key: ("on" if t.default else "off") for key, t in TOGGLES.items()},
            **{key: s.default for key, s in SCALES.items()},
        },
    ),
    SettingPreset("hardcore", "硬核", {"misc.FF": "on", "misc.KC": "off", "misc.MM": "off"}),
    SettingPreset("no_vehicles", "无载具", {"vehicles.L": "off", "vehicles.A": "off"}),
    SettingPreset("no_elites", "无精英兵", {"kits.HERO": "off"}),
    SettingPreset(
        "sir_only",
        "仅制式步枪",
        {
            "weapons.SIR": "on",
            "weapons.S": "off",
            "weapons.LMG": "off",
            "weapons.SMG": "off",
            "weapons.SAR": "off",
            "weapons.SR": "off",
        },
    ),
    SettingPreset("unlimited_mags", "无限弹匣", {"misc.UM": "on"}),
    SettingPreset("double_damage", "双倍伤害", {"scales.BD": "BD3"}),
    SettingPreset("double_tickets", "双倍兵力", {"scales.TC": "TC3"}),
)


def toggle_state(masks: object, toggle: SettingToggle) -> bool | None:
    """按掩码（ServerMasks）读出某个开关是否打开；该组掩码缺失时返回 None。"""
    mask: int | None = getattr(masks, GROUPS[toggle.group].mask_field, None)
    if mask is None:
        return None
    return bool((mask >> toggle.bit) & 1)


def scale_state(masks: object, scale: ScaleSetting) -> ScaleOption | None:
    """按掩码读出某项倍率当前的档位；掩码缺失或该项不是恰好一位为 1 时返回 None。"""
    mask: int | None = getattr(masks, "scale", None)
    if mask is None:
        return None
    hits = [o for o in scale.options if (mask >> o.bit) & 1]
    return hits[0] if len(hits) == 1 else None


def rule_state(masks: object, rule_key: str) -> str | None:
    """某条规则在这台服上的取值（on / off 或选项键）；读不出来时返回 None。"""
    if masks is None:
        return None
    toggle = TOGGLES.get(rule_key)
    if toggle is not None:
        state = toggle_state(masks, toggle)
        return None if state is None else ("on" if state else "off")
    option = scale_state(masks, SCALES[rule_key])
    return option.key if option else None


def rule_mask_field(rule_key: str) -> str:
    """判读这条规则要用的 ServerMasks 字段。"""
    toggle = TOGGLES.get(rule_key)
    return GROUPS[toggle.group].mask_field if toggle else "scale"


MASK_FIELDS: tuple[str, ...] = ("vehicle", "weapon", "kit", "setting", "scale")


def to_ea_filter(rules: Mapping[str, RuleValue]) -> dict[str, dict[str, str]]:
    """把规则转成 filterJson 里的分组：{"vehicles": {"L": "off"}, "scales": {"BD3": "on"}}。"""
    out: dict[str, dict[str, str]] = {}
    for rule_key, value in rules.items():
        if rule_key in SCALES:
            out.setdefault("scales", {})[value] = "on"
            continue
        toggle = TOGGLES[rule_key]
        out.setdefault(GROUPS[toggle.group].ea_key, {})[toggle.key] = value
    return out
