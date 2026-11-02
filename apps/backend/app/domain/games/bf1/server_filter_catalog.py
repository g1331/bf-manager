"""BF1 服务器浏览器的玩法开关目录与掩码判读。

开关清单、顺序、默认值与简体名取自游戏自己的 ``Gamedata.getGameData``（data/gamedata.zh-CN.json
的 settings.Misc / Weapons / Vehicles / Kits），名称与详情页的设置展示一致。Blaze 快照 ATTR 里
每组开关压成一个整数掩码，位序经部署机对照官服与私服实测：

- vehiclemask：bit0 地面载具 L，bit1 空中载具 A
- weaponmask：bit0..9 依次为 M S H E LMG SMG SAR SR KG SIR
- kitmask：bit0..3 为兵种 1..4，bit9 为精英兵种 HERO
- settingmask：bit0..20 与 Misc 清单同序

同一套开关也能写进 EA searchServers 的 filterJson：组内列出的 key 设 on 即要求开、off 即
要求关，没列出的不约束，组内多个 key 取交集。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

RuleValue = Literal["on", "off"]


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
        "规则",
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
class SettingPreset:
    id: str
    label: str
    rules: dict[str, RuleValue]


PRESETS: tuple[SettingPreset, ...] = (
    SettingPreset(
        "vanilla",
        "原版设置",
        {key: ("on" if t.default else "off") for key, t in TOGGLES.items()},
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
)


def toggle_state(masks: object, toggle: SettingToggle) -> bool | None:
    """按掩码（ServerMasks）读出某个开关是否打开；该组掩码缺失时返回 None。"""
    mask: int | None = getattr(masks, GROUPS[toggle.group].mask_field, None)
    if mask is None:
        return None
    return bool((mask >> toggle.bit) & 1)


def to_ea_filter(rules: Mapping[str, RuleValue]) -> dict[str, dict[str, RuleValue]]:
    """把开关规则转成 filterJson 里的分组：{"vehicles": {"L": "off"}, ...}。"""
    out: dict[str, dict[str, RuleValue]] = {}
    for rule_key, value in rules.items():
        toggle = TOGGLES[rule_key]
        out.setdefault(GROUPS[toggle.group].ea_key, {})[toggle.key] = value
    return out
