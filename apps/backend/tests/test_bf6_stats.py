"""BF6：wire 编解码、战绩归一化、名字解析（全部离线）。"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from app.domain.games.bf6 import resolver
from app.domain.games.bf6.wire import (
    CategoryStats,
    Dimension,
    DimensionedStat,
    Player,
    PlayerStats,
    WireError,
    decode_get_stats_response,
    decode_via_jwt_response,
    encode_dimensions_filter,
    encode_get_stats_request,
    encode_get_stats_response,
    encode_player,
)
from app.services.bf6.stats_normalizer import normalize

GLOBAL = (Dimension("global", "global"),)
NOW = datetime(2026, 11, 4, tzinfo=UTC)


def _g(name: str, value: int) -> DimensionedStat:
    return DimensionedStat(name, value, GLOBAL)


def _sample() -> PlayerStats:
    rows = [
        _g("Kills_Total", 100),
        _g("human_kills_total", 80),
        _g("deaths_total", 20),
        _g("score_total", 12000),
        _g("matches_gm_all", 4),
        _g("wins_gm_all", 2),
        _g("losses_gm_all", 2),
        _g("tp_kit", 3600),
        _g("tp_gm_all", 4000),
        _g("shots_fired_total", 500),
        _g("shots_hit_total", 125),
        _g("kills_Headshots_Total", 16),
        _g("distrav_foot_total", 1000),
        _g("distrav_veh_total", 500),
        _g("kw_veh", 4),
        # 武器：一把具体武器 + 一个大类汇总
        _g("kw_wp_mg_l110", 30),
        _g("sfw_wp_mg_l110", 100),
        _g("shw_wp_mg_l110", 25),
        _g("hsw_wp_mg_l110", 8),
        _g("tp_wp_mg_l110", 600),
        _g("kw_wp_mg", 30),
        _g("kw_wp_temp", 36),
        _g("kw_wp_pst_temp", 1),
        _g("kw_wp_pst_m44", 1),
        _g("kw_wp_ar_m4", 5),
        # 载具
        _g("kw_veh_tank_abrams", 3),
        _g("tp_veh_tank_abrams", 120),
        _g("kw_veh_air", 1),
        _g("kw_veh_air_jets", 1),
        # 兵种
        _g("kw_kit_support", 40),
        _g("deaths_kit_support", 5),
        _g("tp_kit_support", 2000),
        _g("tp_kit_assault", 1000),
        # 模式：all 是汇总行，不进模式列表
        _g("kills_gm_cq", 50),
        _g("matches_gm_cq", 2),
        _g("wins_gm_cq", 1),
        _g("tp_gm_cq", 1800),
        _g("kills_gm_all", 70),
        _g("kills_gm_oblitall", 1),
        # 地图：lvlmp 是合计
        _g("matches_lvlmpaftermath", 3),
        _g("wins_lvlmpaftermath", 2),
        _g("losses_lvlmpaftermath", 1),
        _g("tp_lvlmpaftermath", 900),
        _g("matches_lvlmp", 3),
        _g("matches_lvlftpgranite", 1),
        # 负数按 int32 补码传输
        _g("weird_negative", -5),
        # 非 global 维度不进生涯
        DimensionedStat("Kills_Total", 7, (Dimension("GameMode", "cq"),)),
        DimensionedStat(
            "Kills_Total", 10, (Dimension("GameMode", "cq"), Dimension("Season", "Season1"))
        ),
        DimensionedStat(
            "matches_gm_all", 1, (Dimension("GameMode", "cq"), Dimension("Season", "Season1"))
        ),
    ]
    return PlayerStats(
        player=Player(nucleus_id=1008067890273, persona_id=0, platform=7),
        categories=(
            CategoryStats("glacier_sp"),
            CategoryStats(
                "glacier_mp", stats=(("Kills_Total", 100),), dimensioned_stats=tuple(rows)
            ),
        ),
    )


def test_wire_round_trip() -> None:
    original = _sample()
    decoded = decode_get_stats_response(encode_get_stats_response([original]))
    assert decoded == [original]
    negative = next(
        r for r in decoded[0].categories[1].dimensioned_stats if r.name == "weird_negative"
    )
    assert negative.value == -5


def test_request_encoding_skips_defaults() -> None:
    # persona_id=0 不上线
    assert encode_player(Player(nucleus_id=1, persona_id=0, platform=7)) == b"\x08\x01\x18\x07"
    body = encode_get_stats_request(["glacier_mp"], [Player(nucleus_id=1, platform=7)])
    assert body == b"\x0a\x0aglacier_mp\x12\x04\x08\x01\x18\x07"


def test_dimensions_filter_keeps_empty_stat_id() -> None:
    payload = encode_dimensions_filter("", [("global", "global")])
    # 空的 dimensioned_stat_id 也要上线（0a 00），后面是 Dimension{global, global}
    assert payload == b"\x0a\x00\x12\x10\x0a\x06global\x12\x06global"
    body = encode_get_stats_request(["glacier_mp"], [Player(nucleus_id=1)], [payload])
    assert body.endswith(b"\x22\x14" + payload)


def test_via_jwt_response_and_truncated_input() -> None:
    raw = b"\x0a\x03abc\x12\x02\x08\x05"
    token, player = decode_via_jwt_response(raw)
    assert token == "abc"
    assert player.nucleus_id == 5
    with pytest.raises(WireError):
        decode_get_stats_response(b"\x0a\x10short")


def test_normalize_career_and_breakdowns() -> None:
    result = normalize(_sample(), 1008067890273, NOW)
    career = result.career
    assert result.has_data
    assert career.kills == 100
    assert career.human_kills == 80
    assert career.kd == 4.0
    assert career.kpm == 1.333
    assert career.spm == 200.0
    assert career.win_rate == 0.5
    assert career.accuracy == 0.25
    assert career.headshot_rate == 0.16
    assert career.distance_m == 1500
    assert career.vehicle_kills == 4
    assert career.best_class == "support"

    assert [w.id for w in result.weapons] == ["mg_l110", "ar_m4", "pst_m44"]
    l110 = result.weapons[0]
    assert (l110.kills, l110.accuracy, l110.headshot_rate, l110.kpm) == (30, 0.25, 0.2667, 3.0)
    assert l110.damage is None
    # temp（全部武器合计）不单列，pst_temp 归为手枪大类 pst
    assert [w.id for w in result.weapon_categories] == ["mg", "pst"]

    assert [v.id for v in result.vehicles] == ["tank_abrams"]
    assert sorted(v.id for v in result.vehicle_categories) == ["air", "air_jets"]

    assert [k.id for k in result.kits] == ["support", "assault"]
    assert result.kits[0].kd == 8.0

    assert [m.id for m in result.modes] == ["cq"]
    assert result.modes[0].kills == 50
    assert [m.id for m in result.maps] == ["mpaftermath", "ftpgranite"]
    assert (result.maps[0].matches, result.maps[0].win_rate) == (
        3,
        0.6667,
    )  # 来自 global 维度，不是 GameMode 维度的 7


def test_normalize_missing_player_is_empty_not_zero() -> None:
    result = normalize(None, 42, NOW)
    assert not result.has_data
    assert result.career.kills is None
    assert result.career.kd is None
    assert result.weapons == []


# ---------------------------------------------------------------------------
# 名字解析
# ---------------------------------------------------------------------------


def _drop_api(requests: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/highlights"):
            return httpx.Response(200, json={"data": [{"gameEvent": {"id": "EVT1"}}]})
        name = request.url.path.split("/")[2]
        if name == "missing":
            return httpx.Response(206, json={"cause": "MISSING_GAMER_NAME"})
        if name == "noseason":
            return httpx.Response(
                200, json={"noStatsData": {"userId": "7", "playerDisplayName": "NoSeason"}}
            )
        return httpx.Response(
            200,
            json={
                "playerStatsSummary": {
                    "userId": "2306831843",
                    "playerDisplayName": "JackFrags",
                    "platform": "cem_ea_id",
                    "userAvatar": {"small": "s", "large": "l"},
                }
            },
        )

    return httpx.MockTransport(handler)


async def test_resolver_lookup() -> None:
    requests: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=_drop_api(requests)) as http:
        event = await resolver.fetch_current_event(http)
        found = await resolver.lookup(http, "中文 名", event, "psn")
        missing = await resolver.lookup(http, "missing", event, None)
        no_season = await resolver.lookup(http, "noseason", event, "steam")

    assert event == "EVT1"
    assert found is not None
    assert (found.nucleus_id, found.display_name, found.avatar_url) == (
        2306831843,
        "JackFrags",
        "l",
    )
    assert found.has_current_season_stats
    stats_request = requests[1]
    assert stats_request.url.raw_path.startswith(b"/player/%E4%B8%AD%E6%96%87%20%E5%90%8D/stats")
    assert stats_request.url.params["platform"] == "ps3"
    assert stats_request.url.params["eventName"] == "EVT1"
    assert missing is None
    assert no_season is not None and not no_season.has_current_season_stats
    # Steam 没有平台命名空间，不带过滤
    assert "platform" not in requests[3].url.params


def test_normalize_name() -> None:
    assert resolver.normalize_name("  sha11vveE  ") == "sha11vveE"
    assert resolver.normalize_name("中文​玩家") == "中文玩家"
    assert resolver.normalize_name("a   b") == "a b"
