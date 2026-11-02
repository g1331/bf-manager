"""服务器浏览器的玩法筛选：规则解析、EA filter_dict、快照掩码筛选与计数、筛选目录接口。"""

from __future__ import annotations

import pytest
from app.api.errors import ValidationError
from app.domain.games.bf1.server_filter_catalog import PRESETS, TOGGLES
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
    assert len(vanilla.rules) == len(TOGGLES) == 38
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
    assert (f.rules["vehicles.L"].on, f.rules["vehicles.L"].off) == (1, 1)
    # 其它开关在「私服 + 地面载具开」下数
    assert (f.rules["kits.HERO"].on, f.rules["kits.HERO"].off) == (1, 0)
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
    assert [g["id"] for g in body["groups"]] == ["vehicles", "kits", "weapons", "misc"]
    assert sum(len(g["toggles"]) for g in body["groups"]) == 38
    assert any(p["id"] == "hardcore" for p in body["presets"])
