"""服务器浏览器的筛选：校验条件、构造 EA searchServers 的 filter_dict、在全服快照上本地筛选与计数。

EA filterJson 的语义经部署机实测确认：地图 / 模式 / 地区这类多选维度只列选中项设 "on"，
多项取并集，未选中的维度整体省略即不约束；玩法开关组（vehicles / weaponClasses / kits /
misc）里列出的 key 设 on 即要求开、off 即要求关，没列出的不约束，组内多个 key 取交集。

空位（slots）不能下推：EA searchServers 不按实时空位过滤，无论档位怎么设返回集都和无筛选
一致，所以两条路径都在拿到结果后本地过滤。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.api.errors import ValidationError
from app.domain.games.bf1.maps import MapData
from app.domain.games.bf1.server_filter_catalog import (
    PRESETS,
    SETTING_GROUPS,
    TOGGLES,
    RuleValue,
    to_ea_filter,
    toggle_state,
)
from app.schemas.bf1.server import (
    FilterGroupOption,
    FilterPresetOption,
    FilterServerTypeOption,
    FilterToggleOption,
    RuleFacet,
    ServerFacets,
    ServerFilterOptions,
    ServerSummary,
)

# 服务器规模档位（gameSizes 数值 key 全集），与游戏「遊戲規模」筛选项一致
VALID_SIZES: frozenset[int] = frozenset({10, 16, 24, 32, 40, 48, 64})
# 地图 / 模式 / 地区代号全集，复用翻译字典的 key，避免重复维护一份清单
VALID_MAPS: frozenset[str] = frozenset(MapData.MapTeamDict)
VALID_MODES: frozenset[str] = frozenset(MapData.ModeDict)
VALID_REGIONS: frozenset[str] = frozenset(MapData.RegionDict)
# 服务器类型：UNRANKED 实测全网 0 个服，不提供
SERVER_TYPES: tuple[str, ...] = ("OFFICIAL", "RANKED", "PRIVATE")
# 空位（剩余席位）分档，复刻游戏「空位」筛选项
SLOT_BUCKETS: tuple[str, ...] = ("none", "1-5", "6-10", "10+")


def _reject_unknown(values: Iterable[Any], allowed: Iterable[Any], field: str) -> None:
    """拼错或越界的取值直接拒绝，避免静默返回与预期不符的结果。"""
    allowed_set = set(allowed)
    unknown = [v for v in values if v not in allowed_set]
    if unknown:
        raise ValidationError(
            f"{field} 含非法取值: {unknown}",
            details={"field": field, "unknown": unknown},
        )


def parse_rules(raw: list[str] | None) -> dict[str, RuleValue]:
    """把 ``vehicles.L:off`` 形式的规则解析成 {规则键: on/off}；同一开关给了相反的值时拒绝。"""
    if raw and len(raw) > len(TOGGLES):
        raise ValidationError("rules 条数过多", details={"field": "rules"})
    rules: dict[str, RuleValue] = {}
    bad: list[str] = []
    for item in raw or []:
        key, sep, value = item.partition(":")
        if not sep or key not in TOGGLES or value not in ("on", "off"):
            bad.append(item)
            continue
        if rules.get(key, value) != value:
            bad.append(item)
            continue
        rules[key] = "on" if value == "on" else "off"
    if bad:
        raise ValidationError(
            f"rules 含非法取值: {bad}", details={"field": "rules", "unknown": bad}
        )
    return rules


def validate_slots(slots: list[str] | None) -> None:
    if slots:
        _reject_unknown(slots, SLOT_BUCKETS, "slots")


def build_search_filter(
    *,
    name: str | None = None,
    maps: list[str] | None = None,
    modes: list[str] | None = None,
    regions: list[str] | None = None,
    sizes: list[int] | None = None,
    server_types: list[str] | None = None,
    rules: Mapping[str, RuleValue] | None = None,
) -> dict[str, Any]:
    """构造 EA filter_dict 并顺带校验取值。只写入有条件的维度，name 始终写入（空串即不按名称过滤）。"""
    filter_dict: dict[str, Any] = {"name": name or ""}
    if maps:
        _reject_unknown(maps, VALID_MAPS, "maps")
        filter_dict["maps"] = dict.fromkeys(maps, "on")
    if modes:
        _reject_unknown(modes, VALID_MODES, "modes")
        filter_dict["gameModes"] = dict.fromkeys(modes, "on")
    if regions:
        _reject_unknown(regions, VALID_REGIONS, "regions")
        filter_dict["regions"] = dict.fromkeys(regions, "on")
    if sizes:
        _reject_unknown(sizes, VALID_SIZES, "sizes")
        filter_dict["gameSizes"] = {str(size): "on" for size in sizes}
    if server_types:
        _reject_unknown(server_types, SERVER_TYPES, "server_types")
        filter_dict["serverType"] = dict.fromkeys(server_types, "on")
    if rules:
        filter_dict.update(to_ea_filter(rules))
    return filter_dict


def slot_bucket(s: ServerSummary) -> str | None:
    """剩余席位分档；没有人数上限的服务器不参与分档。"""
    if s.max_player_count <= 0:
        return None
    free = s.max_player_count - s.player_count
    if free <= 0:
        return "none"
    if free <= 5:
        return "1-5"
    if free <= 10:
        return "6-10"
    return "10+"


def _rules_ok(s: ServerSummary, rules: Mapping[str, RuleValue], skip: str | None = None) -> bool:
    """服务器满足全部开关规则；读不到对应掩码时按不满足处理。"""
    for key, value in rules.items():
        if key == skip:
            continue
        if s.masks is None or toggle_state(s.masks, TOGGLES[key]) != (value == "on"):
            return False
    return True


def _base_matches(
    items: list[ServerSummary],
    *,
    name: str | None,
    maps: list[str] | None,
    modes: list[str] | None,
    regions: list[str] | None,
    sizes: list[int] | None,
    slots: list[str] | None,
) -> list[ServerSummary]:
    needle = (name or "").casefold()
    return [
        s
        for s in items
        if needle in s.name.casefold()
        and (not maps or s.map_name in maps)
        and (not modes or s.game_mode in modes)
        and (not regions or s.region in regions)
        and (not sizes or s.max_player_count in sizes)
        and (not slots or slot_bucket(s) in slots)
    ]


def filter_summaries(
    items: list[ServerSummary],
    *,
    name: str | None = None,
    maps: list[str] | None = None,
    modes: list[str] | None = None,
    regions: list[str] | None = None,
    sizes: list[int] | None = None,
    server_types: list[str] | None = None,
    rules: Mapping[str, RuleValue] | None = None,
    slots: list[str] | None = None,
) -> list[ServerSummary]:
    """在全服摘要缓存上本地筛选，口径对齐 EA：名称包含匹配且大小写不敏感，多值维度取并集，
    规模按服务器最大人数匹配，开关规则按快照掩码判读。取值合法性由调用方先行校验。
    """
    base = _base_matches(
        items, name=name, maps=maps, modes=modes, regions=regions, sizes=sizes, slots=slots
    )
    return [
        s
        for s in base
        if (not server_types or s.server_type in server_types) and _rules_ok(s, rules or {})
    ]


def compute_facets(
    items: list[ServerSummary],
    *,
    name: str | None = None,
    maps: list[str] | None = None,
    modes: list[str] | None = None,
    regions: list[str] | None = None,
    sizes: list[int] | None = None,
    server_types: list[str] | None = None,
    rules: Mapping[str, RuleValue] | None = None,
    slots: list[str] | None = None,
) -> ServerFacets:
    """每个筛选项选上之后能剩几个服。

    服务器类型与每个开关的计数都撇开自身维度的条件（选了「官服」时「私服」照样显示私服有多少），
    快捷标签的计数是把它的规则叠到当前条件上（同一开关以标签为准）之后的结果数。
    """
    rules = rules or {}
    base = _base_matches(
        items, name=name, maps=maps, modes=modes, regions=regions, sizes=sizes, slots=slots
    )
    type_counts = dict.fromkeys(SERVER_TYPES, 0)
    for s in base:
        if s.server_type in type_counts and _rules_ok(s, rules):
            type_counts[s.server_type] += 1

    typed = [s for s in base if not server_types or s.server_type in server_types]
    rule_counts: dict[str, RuleFacet] = {}
    for key, toggle in TOGGLES.items():
        facet = RuleFacet()
        for s in typed:
            state = toggle_state(s.masks, toggle) if s.masks is not None else None
            if state is None or not _rules_ok(s, rules, skip=key):
                continue
            if state:
                facet.on += 1
            else:
                facet.off += 1
        rule_counts[key] = facet

    preset_counts = {
        p.id: sum(1 for s in typed if _rules_ok(s, {**rules, **p.rules})) for p in PRESETS
    }
    return ServerFacets(server_types=type_counts, rules=rule_counts, presets=preset_counts)


_SERVER_TYPE_LABELS = {"OFFICIAL": "官服", "RANKED": "私服", "PRIVATE": "密码服"}


def server_filter_options() -> ServerFilterOptions:
    return ServerFilterOptions(
        server_types=[
            FilterServerTypeOption(id=t, label=_SERVER_TYPE_LABELS[t]) for t in SERVER_TYPES
        ],
        presets=[FilterPresetOption(id=p.id, label=p.label, rules=p.rules) for p in PRESETS],
        groups=[
            FilterGroupOption(
                id=g.id,
                label=g.label,
                toggles=[
                    FilterToggleOption(key=t.rule_key, label=t.label, default=t.default)
                    for t in g.toggles
                ],
            )
            for g in SETTING_GROUPS
        ],
    )
