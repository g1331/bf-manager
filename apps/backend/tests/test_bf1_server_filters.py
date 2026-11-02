"""服务器浏览器的玩法筛选：规则解析、EA filter_dict、快照掩码筛选与计数、筛选目录接口。"""

from __future__ import annotations

import pytest
from app.api.errors import ValidationError
from app.domain.games.bf1.server_filter_catalog import (
    PRESETS,
    SCALES,
    TOGGLES,
    rule_state,
    to_ea_filter,
)
from app.domain.games.bf1.server_settings import settings_from_masks
from app.schemas.bf1.server import ServerMasks, ServerSummary
from app.services.bf1 import server_service
from app.services.bf1.server_filters import (
    build_search_filter,
    compute_facets,
    filter_summaries,
    parse_rules,
)
from app.services.bf1.server_service import BF1ServerService

# 原版默认：载具全开、兵种全开、武器除制式步枪外全开、规则按游戏默认
VANILLA = ServerMasks(vehicle=3, weapon=511, kit=527, setting=54715, scale=9362)
# 硬核：友伤开、击杀镜头与 HUD 关；无载具；无精英兵
HARDCORE = ServerMasks(vehicle=0, weapon=511, kit=15, setting=(54715 | 4) & ~1 & ~2, scale=9362)
# 纯制式步枪：SIR 开，霰弹 / 轻机 / 冲锋 / 半自动 / 栓动关
SIR = ServerMasks(vehicle=3, weapon=1 | 4 | 8 | 256 | 512, kit=527, setting=54715, scale=9362)


def _s(
    gid: int, server_type: str, masks: ServerMasks | None, *, players: int = 10
) -> ServerSummary:
    return ServerSummary(
        server_id=0,
        game_id=gid,
        name=f"srv{gid}",
        player_count=players,
        max_player_count=64,
        server_type=server_type,
        masks=masks,
    )


ITEMS = [
    _s(1, "OFFICIAL", VANILLA, players=60),
    _s(2, "RANKED", HARDCORE, players=50),
    _s(3, "RANKED", SIR, players=30),
    _s(4, "PRIVATE", VANILLA, players=5),
    _s(5, "RANKED", None, players=40),
]


def test_vanilla_preset_matches_game_defaults() -> None:
    vanilla = next(p for p in PRESETS if p.id == "vanilla")
    # 38 个开关 + 5 项倍率
    assert len(vanilla.rules) == len(TOGGLES) + len(SCALES) == 43
    assert [s.game_id for s in filter_summaries(ITEMS, rules=vanilla.rules)] == [1, 4]


def test_parse_rules() -> None:
    assert parse_rules(["vehicles.L:off", "misc.3S:on"]) == {
        "vehicles.L": "off",
        "misc.3S": "on",
    }
    assert parse_rules(None) == {}
    # 重复且一致可以，相反值、未知键、坏格式都拒绝
    assert parse_rules(["kits.HERO:off", "kits.HERO:off"]) == {"kits.HERO": "off"}
    for bad in (["kits.HERO:off", "kits.HERO:on"], ["kits.X:on"], ["kits.HERO"], ["kits.HERO:1"]):
        with pytest.raises(ValidationError):
            parse_rules(bad)


def test_build_search_filter_pushes_types_and_rules() -> None:
    f = build_search_filter(
        server_types=["RANKED", "PRIVATE"],
        rules={"vehicles.L": "off", "weapons.SIR": "on", "misc.FF": "on", "kits.HERO": "off"},
    )
    assert f == {
        "name": "",
        "serverType": {"RANKED": "on", "PRIVATE": "on"},
        "vehicles": {"L": "off"},
        "weaponClasses": {"SIR": "on"},
        "misc": {"FF": "on"},
        "kits": {"HERO": "off"},
    }
    with pytest.raises(ValidationError):
        build_search_filter(server_types=["UNRANKED"])


def test_filter_summaries_by_type_rules_and_slots() -> None:
    assert [s.game_id for s in filter_summaries(ITEMS, server_types=["RANKED"])] == [2, 3, 5]
    # 读不到掩码的服不满足任何开关规则
    hero_off = filter_summaries(ITEMS, rules={"kits.HERO": "off"})
    assert [s.game_id for s in hero_off] == [2]
    sir = filter_summaries(ITEMS, rules={"weapons.SIR": "on", "weapons.SR": "off"})
    assert [s.game_id for s in sir] == [3]
    # 64 人服：60 人剩 4 位、50 人剩 14 位
    assert [s.game_id for s in filter_summaries(ITEMS, slots=["1-5"])] == [1]


def test_facets_ignore_own_dimension() -> None:
    f = compute_facets(ITEMS, server_types=["RANKED"], rules={"vehicles.L": "on"})
    # 类型计数撇开类型条件，只受载具规则约束：2 号无载具被排除，5 号无掩码被排除
    assert f.server_types == {"OFFICIAL": 1, "RANKED": 1, "PRIVATE": 1}
    # 地面载具的计数撇开自身规则，在私服里数开 / 关
    assert f.rules["vehicles.L"] == {"on": 1, "off": 1}
    # 其它开关在「私服 + 地面载具开」下数
    assert f.rules["kits.HERO"] == {"on": 1, "off": 0}
    # 倍率按档位计数：私服里开地面载具的只有 3 号，默认档
    assert f.rules["scales.BD"] == {"BD1": 0, "BD2": 1, "BD3": 0, "BD4": 0}
    # 快捷标签的规则叠到当前条件上，同一开关以标签为准
    assert f.presets["no_vehicles"] == 1
    assert f.presets["sir_only"] == 1
    assert f.presets["vanilla"] == 0


async def test_search_filters_snapshot_by_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_read() -> list[ServerSummary]:
        return ITEMS

    def no_ea(_db: object) -> object:
        raise AssertionError("快照有掩码时不应请求 EA")

    monkeypatch.setattr(server_service, "read_server_snapshot", fake_read)
    monkeypatch.setattr(server_service, "get_bf1_client", no_ea)
    res = await BF1ServerService(object()).search(  # type: ignore[arg-type]
        rules=["kits.HERO:on"], server_types=["OFFICIAL", "PRIVATE"]
    )
    assert [s.game_id for s in res.items] == [1, 4]
    assert res.facets is not None and res.facets.server_types["RANKED"] == 1


class _FakeClient:
    def __init__(self) -> None:
        self.filters: list[dict] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None

    async def searchServers(self, **kw: object) -> dict:  # noqa: N802
        self.filters.append(kw["filter_dict"])  # type: ignore[arg-type]
        servers = [
            {"name": "full", "gameId": "8", "serverType": "RANKED", "slots": _slots(64, 64)},
            {"name": "open", "gameId": "9", "serverType": "RANKED", "slots": _slots(20, 64)},
        ]
        return {"result": {"gameservers": servers}}


def _slots(cur: int, cap: int) -> dict:
    return {"Soldier": {"current": cur, "max": cap}}


async def test_search_falls_back_to_ea_when_snapshot_has_no_masks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """快照失败时缓存来自 searchServers，没有掩码，带开关规则就得交给 EA 筛。"""

    async def fake_read() -> list[ServerSummary]:
        return [_s(1, "RANKED", None)]

    client = _FakeClient()
    monkeypatch.setattr(server_service, "read_server_snapshot", fake_read)
    monkeypatch.setattr(server_service, "get_bf1_client", lambda _db: client)
    res = await BF1ServerService(object()).search(  # type: ignore[arg-type]
        rules=["vehicles.A:off"], slots=["10+"]
    )
    assert client.filters[0]["vehicles"] == {"A": "off"}
    # 空位 EA 不过滤，拿回来后本地过滤；EA 路径不给计数
    assert [s.game_id for s in res.items] == [9]
    assert res.facets is None


async def test_filter_options_route(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/v1/bf1/servers/filter-options")
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body["server_types"]] == ["OFFICIAL", "RANKED", "PRIVATE"]
    assert [g["id"] for g in body["groups"]] == ["vehicles", "kits", "weapons", "misc", "scales"]
    assert sum(len(g["rules"]) for g in body["groups"]) == 43
    bd = body["groups"][-1]["rules"][0]
    # 倍率选项按大小排，标签与详情页一样用百分比
    assert [o["label"] for o in bd["options"]] == ["50%", "100%", "125%", "200%"]
    assert bd["default"] == "BD2"
    assert any(p["id"] == "hardcore" for p in body["presets"])


# 真服实测：TURKIYE VATAN SUNUCUSU（%200Dmg），EA 详情为 重生 0.5、时限 0.0、兵力 2.0、伤害 2.0、载具 0.5
DMG200 = ServerMasks(vehicle=3, weapon=511, kit=527, setting=54715, scale=10316)


def test_scale_mask_decoding_matches_real_server() -> None:
    assert {k: rule_state(DMG200, k) for k in SCALES} == {
        "scales.BD": "BD3",
        "scales.TC": "TC3",
        "scales.SR": "SR1",
        "scales.VR": "VR1",
        "scales.RT": "RT1",
    }
    # 默认 9362 即全部默认档；不是恰好一位的掩码读不出
    assert rule_state(VANILLA, "scales.RT") == "RT1"
    assert rule_state(ServerMasks(scale=0), "scales.BD") is None
    assert rule_state(ServerMasks(scale=(1 << 9) | (1 << 11)), "scales.BD") is None


def test_scale_rules_parse_filter_and_push_down() -> None:
    assert parse_rules(["scales.BD:BD3", "misc.FF:on"]) == {"scales.BD": "BD3", "misc.FF": "on"}
    # 倍率单选：同一项给两个档位、档位不属于该项都拒绝
    for bad in (["scales.BD:BD1", "scales.BD:BD3"], ["scales.BD:TC1"], ["scales.XX:XX1"]):
        with pytest.raises(ValidationError):
            parse_rules(bad)
    assert to_ea_filter({"scales.BD": "BD3", "scales.TC": "TC3", "kits.HERO": "off"}) == {
        "scales": {"BD3": "on", "TC3": "on"},
        "kits": {"HERO": "off"},
    }
    items = [*ITEMS, _s(6, "RANKED", DMG200)]
    assert [s.game_id for s in filter_summaries(items, rules={"scales.BD": "BD3"})] == [6]
    double = next(p for p in PRESETS if p.id == "double_damage")
    assert compute_facets(items).presets[double.id] == 1


def test_settings_from_masks_matches_detail_shape() -> None:
    settings, descriptions = settings_from_masks(DMG200)
    assert settings["Scales"] == {
        "子弹伤害": "2.0",
        "兵力值": "2.0",
        "重生时间": "0.5",
        "载具重置时间": "0.5",
        "回合时限": "0.0",
    }
    assert settings["Vehicles"] == {"地面载具": "on", "空中载具": "on"}
    assert settings["Weapons"]["制式步枪"] == "off"
    assert settings["Misc"]["友军炮火"] == "off"
    assert descriptions["友军炮火"]
    # 掩码缺失的组整组省略
    assert set(settings_from_masks(ServerMasks(vehicle=0))[0]) == {"Vehicles"}


def test_catalog_labels_match_game_data() -> None:
    """筛选里的名称要和详情页（gamedata 简体名）一致。"""
    import json
    from pathlib import Path

    import app.domain.games.bf1 as pkg

    data = json.loads(
        (Path(pkg.__file__).parent / "data" / "gamedata.zh-CN.json").read_text(encoding="utf-8")
    )["settings"]
    names = {(g, i["filterKey"]): i["name"] for g, items in data.items() for i in items}
    groups = {"vehicles": "Vehicles", "kits": "Kits", "weapons": "Weapons", "misc": "Misc"}
    for t in TOGGLES.values():
        assert names[(groups[t.group], t.key)] == t.label
    for sc in SCALES.values():
        assert names[("Scales", sc.name)] == sc.label
        opts = next(i for i in data["Scales"] if i["filterKey"] == sc.name)["options"]
        assert {o.key: o.value for o in sc.options} == opts
        assert (
            sc.default
            == next(i for i in data["Scales"] if i["filterKey"] == sc.name)["defaultOption"]
        )


async def test_detail_settings_fall_back_to_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_read() -> list[ServerSummary]:
        return [_s(7, "OFFICIAL", DMG200), _s(8, "OFFICIAL", None)]

    monkeypatch.setattr(server_service, "read_server_snapshot", fake_read)
    settings, _ = await server_service._settings_from_snapshot(7)
    assert settings["Scales"]["子弹伤害"] == "2.0"
    # 不在快照里、或没有掩码的服仍然为空
    assert await server_service._settings_from_snapshot(8) == ({}, {})
    assert await server_service._settings_from_snapshot(9) == ({}, {})
