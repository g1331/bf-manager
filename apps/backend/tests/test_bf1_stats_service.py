"""BF1 战绩组装的纯函数单测

_build_summary / _build_soldiers 从 Blaze 生涯数据（BlazeCareer）组装综合战绩与兵种分布，
_build_weapons / _build_vehicles 按武器目录把 Blaze 统计组装成列表并关联皮肤。
"""

from __future__ import annotations

import pytest
from app.domain.games.bf1 import blaze_catalog
from app.domain.games.bf1.blaze_stats import career_stat_names, parse_career
from app.domain.games.bf1.career_profile import MAPS, parse_profile, profile_stat_names
from app.domain.games.bf1.maps import MapData, normalize_emblem_url
from app.services.bf1 import stats_service
from app.services.bf1.stats_service import (
    _build_detail,
    _build_platoon,
    _build_soldiers,
    _build_summary,
    _build_vehicles,
    _build_weapons,
    _extract_kit_skin_candidates,
    _extract_weapon_skin_candidates,
    _kit_number_for_category,
    _parse_online,
    _pick_skin,
    _slot_sorted_guids,
)


def _make_values() -> dict[str, float]:
    """Blaze Stats.getStats 合并后的 {统计名: 数值}（截取关键统计）"""
    return {
        "kills": 35_000.0,
        "c___d_g": 12_000.0,
        "c_mwin__roo_g": 980.0,
        "c_mlos__roo_g": 540.0,
        "c___kak_g": 4_800.0,
        "c___re_g": 2_100.0,
        "c___h_g": 9_500.0,
        "c___r_g": 1_200.0,
        "c___dt_g": 320.0,
        "c___k_ghvs": 32.0,
        "c___hsd_ghva": 412.5,
        "c_av__ki_g": 6_800.0,
        "score": 12_000_000.0,
        "rank": 121.0,
        "skill": 418.0,
        "c_as__ks_g": 8_000.0,
        "c_as__sa_g": 220_000.0,
        "sc_assault": 1_200_000.0,
        "c_md__ks_g": 15_000.0,
        "c_md__sa_g": 540_000.0,
        "sc_medic": 2_800_000.0,
        "c_sc__ks_g": 4_000.0,
        "c_sc__sa_g": 180_000.0,
        "sc_scout": 720_000.0,
        # 精英兵只计入总时长
        "c_kfk__sa_g": 60_000.0,
    }


def test_career_stat_names_cover_every_parsed_stat() -> None:
    # parse_career 读到的统计名都必须在请求名单里，否则线上会一直按 0 处理
    names = {n for ns in career_stat_names().values() for n in ns}
    assert set(_make_values()) <= names


def _profile_values() -> dict[str, float]:
    """战绩页完整生涯：在 _make_values 之外加上荣誉、战斗、模式、精英兵、地图、勋带"""
    return {
        **_make_values(),
        "c_fip__psx_g": 12.0,
        "c___bc_g": 85.0,
        "c_aA__ga_g": 9_000.0,
        "c_mA__ga_g": 40.0,
        "c___hsh_g": 7_000.0,
        "c___sfw_g": 400_000.0,
        "c___shw_g": 100_000.0,
        "c___nk_ghva": 9.0,
        "c___rs_g": 300.0,
        "c___ccp_g": 2_000.0,
        "c_mwin_mgc_roo_g": 600.0,
        "c_mlos_mgc_roo_g": 400.0,
        "sc_conquest": 7_000_000.0,
        "c_mwin_mgb_roo_g": 300.0,
        "c_mlos_mgb_roo_g": 100.0,
        "sc_operations": 4_000_000.0,
        "c_st__ks_g": 150.0,
        "c_st__sa_g": 9_000.0,
        "c_in__sa_g": 600.0,
        "c_in__ks_g": 40.0,
        "c_lmp2__so_g": 50_000.0,
        "c_xp1mp1__so_g": 90_000.0,
        "c_xp3mp4__so_g": 3_000.0,
        "c_xp4mp6__so_g": 0.4,
        "c___roo_g": 1_520.0,
        "c___ro_g": 1_900.0,
        "c___sas_g": 3_600.0,
        "r01_00": 30.0,
        "r33_00": 120.0,
        "r40_00": 0.0,
        "r46_00": 2.0,
    }


def _full_values() -> dict[str, float]:
    """EA 把请求的统计全都返回（没有的为 0），再盖上 _profile_values"""
    zeros = {n: 0.0 for ns in profile_stat_names().values() for n in ns}
    return zeros | _profile_values()


def test_profile_stat_names_cover_every_parsed_stat() -> None:
    names = {n for ns in profile_stat_names().values() for n in ns}
    assert set(_profile_values()) <= names
    # 计分板批量查询的名单不能跟着变大
    assert len({n for ns in career_stat_names().values() for n in ns}) < 40
    # 32 张多人图各一个统计，不重复，和地图表的代号一致
    assert len({name for _, name in MAPS.values()}) == len(MAPS) == 32
    assert set(MAPS) == set(MapData.MapTeamDict)


def test_build_detail_profile_sections() -> None:
    values = _full_values()
    d = _build_detail(7, parse_profile(values), values)
    assert d.summary.kills == 35_000
    assert d.honors is not None and (d.honors.mvp, d.honors.ace_squad, d.honors.medals) == (
        12,
        85,
        40,
    )
    assert d.combat is not None
    assert (d.combat.accuracy, d.combat.headshot_rate) == (0.25, 0.2)
    assert d.combat.max_nemesis_streak == 9
    assert d.teamwork is not None and (d.teamwork.resupplies, d.teamwork.flag_captures) == (
        300,
        2_000,
    )
    # 没打过的模式不列；空中突袭没有得分
    assert [(m.mode, m.wins, m.losses, m.win_rate, m.score) for m in d.modes] == [
        ("conquest", 600, 400, 0.6, 7_000_000),
        ("operations", 300, 100, 0.75, 4_000_000),
    ]
    assert [(k.kit, k.kills, k.time_seconds) for k in d.elite_kits] == [
        ("sentry", 150, 9_000),
        ("infiltrator", 40, 600),
    ]
    # 按时长倒序，不到 1 秒的不算玩过
    assert [(m.map, m.time_seconds) for m in d.maps] == [
        ("MP_Verdun", 90_000),
        ("MP_Chateau", 50_000),
        ("MP_Harbor", 3_000),
    ]
    assert d.ribbons is not None and len(d.ribbons) == 47
    counts = {r.code: r.count for r in d.ribbons}
    assert (counts["r01"], counts["r33"], counts["r40"], counts["r46"], counts["r02"]) == (
        30,
        120,
        0,
        2,
        0,
    )
    assert d.misc is not None
    assert (d.misc.completion_rate, d.misc.spectator_seconds) == (1_520 / 1_900, 3_600)


def test_build_detail_ribbons_none_when_a_category_is_missing() -> None:
    # 勋带 3 个类别分开请求，缺了一类就不能当成全是 0
    values = {k: v for k, v in _profile_values().items() if k != "r46_00"}
    d = _build_detail(7, parse_profile(values), values)
    assert d.ribbons is None
    empty = _build_detail(7, parse_profile({}), {})
    assert (empty.modes, empty.elite_kits, empty.maps, empty.ribbons) == ([], [], None, None)
    assert empty.combat is not None and empty.combat.accuracy is None


def test_missing_category_is_unknown_not_zero() -> None:
    # statcategory3 没返回这个人：入侵者击杀未知、地图不全，不能显示成 0 / 残缺排行
    values = {
        k: v
        for k, v in _full_values().items()
        if k not in profile_stat_names()["player_statcategory3"]
    }
    p = parse_profile(values)
    assert not p.complete
    d = _build_detail(7, p, values)
    assert d.maps is None
    assert [(k.kit, k.kills) for k in d.elite_kits] == [("sentry", 150), ("infiltrator", None)]
    assert parse_profile(_full_values()).complete


async def test_get_detailed_stats_uses_cache(monkeypatch) -> None:
    calls: list[int] = []

    full = True

    async def fake_fetch(db, pids, names):
        calls.append(len(names))
        values = _full_values()
        if not full:
            values = {k: v for k, v in values.items() if k not in names["player_statcategory4"]}
        return {pids[0]: values}

    store: dict[str, object] = {}

    class FakeCache:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ttl=None):
            store[key] = value

    async def fake_get_cache():
        return FakeCache()

    monkeypatch.setattr(stats_service, "fetch_stats", fake_fetch)
    monkeypatch.setattr(stats_service, "get_cache", fake_get_cache)
    svc = stats_service.BF1StatsService(db=None)  # type: ignore[arg-type]
    first = await svc.get_detailed_stats(9)
    second = await svc.get_detailed_stats(9)
    assert calls == [7]  # 一次查询 7 个类别，第二次走缓存
    assert second == first
    assert second.soldiers and second.soldiers[0].class_name == first.soldiers[0].class_name
    # 结构对不上的旧条目当作没命中，查到后覆盖，下一次就走缓存
    store[stats_service.CAREER_CACHE_KEY.format(9)] = {"summary": "broken"}
    assert await svc.get_detailed_stats(9) == first
    assert await svc.get_detailed_stats(9) == first
    assert calls == [7, 7]
    # 有类别没返回：照常返回但不缓存，下一次重新查
    store.clear()
    full = False
    assert (await svc.get_detailed_stats(9)).maps is None
    assert (await svc.get_detailed_stats(9)).maps is None
    assert calls == [7, 7, 7, 7]
    assert not store


def test_parse_career_rounds_int_fields_and_sums_time() -> None:
    c = parse_career({**_make_values(), "c___kak_g": 4_800.4})
    assert c.assists == 4_800
    assert c.seconds == 220_000 + 540_000 + 180_000 + 60_000
    assert c.best_kit == "medic"
    assert parse_career({}).best_kit is None


def test_build_summary_extracts_all_fields() -> None:
    s = _build_summary(901001001, parse_career(_make_values()))
    assert s.persona_id == 901001001
    assert s.kills == 35_000
    assert s.deaths == 12_000
    assert s.wins == 980
    assert s.losses == 540
    assert s.kd == 35_000 / 12_000
    assert s.time_played_seconds == 1_000_000
    assert s.kpm == 35_000 / 1_000_000 * 60
    assert s.sps == 12_000_000 / 1_000_000
    assert s.rank == 121
    assert s.skill == 418.0
    assert s.vehicle_kills == 6_800
    assert s.infantry_kills == 28_200
    assert s.assists == 4_800
    assert s.revives == 2_100
    assert s.heals == 9_500
    assert s.repairs == 1_200
    assert s.dogtags == 320
    assert s.max_killstreak == 32
    assert s.longest_headshot_meters == 412.5
    assert s.best_class == "medic"


def test_build_summary_handles_empty_career() -> None:
    s = _build_summary(42, parse_career({}))
    assert s.kills == 0
    assert s.kd is None  # deaths 为 0 时不计算 kd
    assert s.kpm is None
    assert s.sps is None
    assert s.rank is None
    assert s.assists is None
    assert s.longest_headshot_meters is None
    assert s.best_class is None


def test_build_soldiers_extracts_class_distribution() -> None:
    soldiers = _build_soldiers(parse_career(_make_values()))
    # 没玩过的兵种不列
    assert [s.class_name for s in soldiers] == ["assault", "medic", "scout"]
    medic = soldiers[1]
    assert medic.kills == 15_000
    assert medic.score == 2_800_000
    assert medic.time_seconds == 540_000
    # 序列化别名验证：JSON key 应为 "class"
    dumped = medic.model_dump(by_alias=True)
    assert dumped["class"] == "medic"
    assert "class_name" not in dumped


def test_parse_online_player_in_server() -> None:
    res = {"result": {"42": {"name": "TestServer #1", "gameId": "123"}}}
    s = _parse_online(res, 42)
    assert s.is_online is True
    assert s.server_name == "TestServer #1"
    assert s.game_id == 123


def test_parse_online_player_offline_when_value_null() -> None:
    # EA 对离线玩家返回 {str(pid): null}
    res = {"result": {"42": None}}
    s = _parse_online(res, 42)
    assert s.is_online is False
    assert s.server_name is None


def test_parse_online_unknown_when_pid_missing_or_bad_shape() -> None:
    # pid 缺席、result 非字典、整体非字典 → 无法判定
    assert _parse_online({"result": {"99": None}}, 42).is_online is None
    assert _parse_online({"result": []}, 42).is_online is None
    assert _parse_online("error string", 42).is_online is None


def _platoon_result() -> dict:
    # 取自部署机实测 getActivePlatoon 返回（pid 1005880910785）
    return {
        "result": {
            "guid": "ca53e7b1-aeac-4440-802f-683453dc6947",
            "name": "Digital Illusions",
            "size": 100,
            "description": "DICE Official Platoon #3",
            "tag": "DICE",
            "emblem": "https://eaassets-a.akamaihd.net/battlelog/bf-emblems/prod_default/exclusive/[SIZE]/DICE.[FORMAT]",
            "verified": True,
        }
    }


def test_build_platoon_extracts_fields_and_expands_emblem() -> None:
    p = _build_platoon(_platoon_result())
    assert p is not None
    assert p.tag == "DICE"
    assert p.name == "Digital Illusions"
    assert p.size == 100
    assert p.verified is True
    # emblem 占位符已展开为可加载 URL
    assert "[SIZE]" not in (p.emblem_url or "")
    assert "[FORMAT]" not in (p.emblem_url or "")
    assert p.emblem_url == (
        "https://eaassets-a.akamaihd.net/battlelog/bf-emblems/prod_default/exclusive/512/DICE.png"
    )


def test_build_platoon_none_when_no_platoon() -> None:
    # EA 对无战队玩家返回 result=None
    assert _build_platoon({"result": None}) is None
    assert _build_platoon({"result": []}) is None
    assert _build_platoon("error string") is None


def test_normalize_emblem_url_handles_ugc_and_empty() -> None:
    ugc = "https://x/ugc/453/495/3289737051/[SIZE].[FORMAT]?v=1628495354"
    assert normalize_emblem_url(ugc) == "https://x/ugc/453/495/3289737051/512.png?v=1628495354"
    assert normalize_emblem_url(None) is None
    assert normalize_emblem_url("") is None


# ----------------------------- 皮肤提取与拼装 -----------------------------

# 皮肤静态表中的真实条目，用于 _pick_skin / _build_* 的命中断言
_WEAPON_SKIN_GUID = "B05B7722-FEF7-4659-9631-481C66DD5944"  # 普魯士人 / Superior
_VEHICLE_SKIN_GUID = "6E5FDF7A-B920-4728-8019-056A4AEE130E"  # M1917 獎盃 (極稀有) / Superior
_FAKE_GUID = "00000000-0000-0000-0000-000000000000"


def test_slot_sorted_guids_orders_by_slot_number() -> None:
    # 上游槽位键无序，按槽位号升序展开
    assert _slot_sorted_guids({"4": "D", "0": "A", "2": "B"}) == ["A", "B", "D"]


def test_slot_sorted_guids_skips_malformed_entries() -> None:
    assert _slot_sorted_guids({"0": "", "1": None, "2": 3, "3": "G"}) == ["G"]
    assert _slot_sorted_guids(None) == []
    assert _slot_sorted_guids(["G"]) == []


def test_extract_weapon_skin_candidates_normalizes_guid_case() -> None:
    result = {"weapons": {"ab-12": {"1": "g1", "0": "g0"}, "cd-34": {}}}
    assert _extract_weapon_skin_candidates(result) == {"AB-12": ["g0", "g1"]}


def test_extract_weapon_skin_candidates_degrades_on_malformed() -> None:
    assert _extract_weapon_skin_candidates(None) == {}
    assert _extract_weapon_skin_candidates("网络超时!") == {}
    assert _extract_weapon_skin_candidates({"weapons": None}) == {}
    assert _extract_weapon_skin_candidates({"kits": {}}) == {}


def test_extract_kit_skin_candidates_takes_first_preset() -> None:
    result = {"kits": {"17": [{"0": "g0", "1": "g1"}], "12": [{}], "8": "bogus", "5": []}}
    assert _extract_kit_skin_candidates(result) == {"17": ["g0", "g1"]}


def test_extract_kit_skin_candidates_degrades_on_malformed() -> None:
    assert _extract_kit_skin_candidates(None) == {}
    assert _extract_kit_skin_candidates({"kits": []}) == {}


@pytest.mark.parametrize(
    ("sort_order", "name", "expected"),
    [
        (5, "重型坦克", "17"),
        (4, "巡航坦克", "12"),
        (6, "輕型坦克", "14"),
        (7, "火砲裝甲車", "15"),
        (8, "攻擊坦克", "20"),
        (9, "突擊裝甲車", "22"),
        (1, "轟炸機", "16"),
        (2, "重型轟炸機", "21"),
        # 飞船 / 驱逐舰 的 sortOrder 同为 14，靠分类名区分
        (14, "飞船", "24"),
        (14, "驱逐舰", "23"),
        # 无已知 kit 编号的分类不展示皮肤
        (0, "攻擊機", None),
        (3, "戰鬥機", None),
        (10, "地面載具", None),
        (None, None, None),
        ("5", "未知分类", None),
    ],
)
def test_kit_number_for_category(sort_order, name, expected) -> None:
    assert _kit_number_for_category(sort_order, name) == expected


def test_pick_skin_returns_first_table_hit() -> None:
    # 槽位中混有非皮肤物件 guid，应跳过未命中项取第一个命中的
    skin = _pick_skin([_FAKE_GUID, _WEAPON_SKIN_GUID])
    assert skin is not None
    assert skin["name"] == "普鲁士人"
    assert skin["rarity"] == "Superior"
    assert skin["image"].startswith("https://eaassets-a.akamaihd.net/battlelog/battlebinary/")


def test_pick_skin_none_when_no_hit() -> None:
    assert _pick_skin([_FAKE_GUID]) is None
    assert _pick_skin([]) is None
    assert _pick_skin(None) is None


_WEAPONS = {
    "wLMGPara": {
        "name": "帕拉貝倫 MG14/17",
        "category": "輕機槍",
        "guid": "ab-12",
        "image": "[BB_PREFIX]/gamedata/Tunguska/1/2/PARABELLUM-123.png",
        "order": 2,
        "cat": "player_weapons2",
        "stats": {
            "kills": "c_wLMGPara__kw_g",
            "seconds": "c_wLMGPara__sw_g",
            "shots": "c_wLMGPara__sfw_g",
            "hits": "c_wLMGPara__shw_g",
            "headshots": "c__wLMGPara_hsh_g",
        },
    },
    # Gateway 没有的条目：无 guid、无图片
    "wSPMask": {
        "name": "防毒面具",
        "category": "配備",
        "image": None,
        "order": 99001,
        "cat": "player_weapons4",
        "stats": {
            "kills": "c_wSPMask__kw_g",
            "seconds": "c_wSPMask__sw_g",
            "shots": "c_wSPMask__sfw_g",
        },
    },
    # Blaze 没有单项统计的配备：stats 为空，总是列出
    "9BCDB1F5": {
        "name": "繃帶包",
        "category": "配備",
        "guid": "9BCDB1F5",
        "image": "[BB_PREFIX]/gamedata/tunguska/29/31/GadgetBandages-1d1fc900.png",
        "order": 3,
        "label": None,
        "cat": None,
        "stats": {},
    },
    "wUnused": {
        "name": "沒用過",
        "category": "配備",
        "order": 1,
        "cat": "player_weapons1",
        "stats": {"kills": "c_wUnused__kw_g", "seconds": "c_wUnused__sw_g"},
    },
}
_WEAPON_VALUES = {
    "c_wLMGPara__kw_g": 500.0,
    "c_wLMGPara__sw_g": 3600.0,
    "c_wLMGPara__sfw_g": 100.0,
    "c_wLMGPara__shw_g": 300.0,
    "c__wLMGPara_hsh_g": 50.0,
    "c_wSPMask__kw_g": 3.0,
    "c_wSPMask__sw_g": 0.0,
    "c_wSPMask__sfw_g": 0.0,
}

_VEHICLES = {
    "taHtA7V": {
        "name": "A7V 重型坦克",
        "category": "重型坦克",
        "sort_order": 5,
        "image": "[BB_PREFIX]/gamedata/Tunguska/3/4/A7V-456.png",
        "order": 0,
        "cat": "player_statcategory",
        "stats": {
            "kills": "c_taHtA7V__ki_g",
            "seconds": "c_taHtA7V__si_g",
            "destroyed": "c__taHtA7V_di_g",
        },
    },
    "ShDeLa": {
        "name": "L 级驱逐舰",
        "category": "驱逐舰",
        "sort_order": 14,
        "order": 1,
        "cat": "player_statcategory3",
        "stats": {"kills": "c_ShDeLa__ki_g", "seconds": "c_ShDeLa__si_g"},
    },
    "plAtHal": {
        "name": "哈尔伯施塔特 CL.II 攻击机",
        "category": "攻击机",
        "sort_order": 0,
        "order": 2,
        "cat": "player_statcategory",
        "stats": {"kills": "c_plAtHal__ki_g", "seconds": "c_plAtHal__si_g"},
    },
}
_VEHICLE_VALUES = {
    "c_taHtA7V__ki_g": 800.0,
    "c_taHtA7V__si_g": 7200.0,
    "c__taHtA7V_di_g": 60.0,
    "c_ShDeLa__ki_g": 5.0,
    "c_plAtHal__ki_g": 30.0,
}


@pytest.fixture
def fake_catalog(monkeypatch):
    tables = {"weapons": _WEAPONS, "vehicles": _VEHICLES}
    monkeypatch.setattr(stats_service, "catalog", lambda kind: tables[kind])


def test_build_weapons_maps_catalog_and_skips_unused(fake_catalog) -> None:
    weapons = _build_weapons(_WEAPON_VALUES, {})
    # 按 Gateway 顺序排列，没用过的不列，无统计的配备照列，目录外的 Blaze 独有条目也在
    assert [w.name for w in weapons] == ["帕拉貝倫 MG14/17", "繃帶包", "防毒面具"]
    para = weapons[0]
    assert para.kills == 500
    assert para.headshots == 50
    assert para.time_seconds == 3600
    # 命中率用 hits/shots 自算（霰弹枪多弹丸可 > 100）
    assert para.accuracy == 300.0
    assert para.category == "輕機槍"
    assert para.image == (
        "https://eaassets-a.akamaihd.net/battlelog/battlebinary/gamedata/Tunguska/1/2/PARABELLUM-123.png"
    )
    bandage = weapons[1]
    assert (bandage.kills, bandage.time_seconds, bandage.accuracy) == (None, None, None)
    assert bandage.image is not None
    mask = weapons[2]
    assert mask.accuracy is None
    assert mask.image is None
    assert mask.time_seconds is None


def test_stat_names_skips_entries_without_stats(monkeypatch) -> None:
    monkeypatch.setattr(blaze_catalog, "catalog", lambda kind: _WEAPONS)
    names = blaze_catalog.stat_names("weapons")
    assert None not in names
    assert names["player_weapons4"] == [
        "c_wSPMask__kw_g",
        "c_wSPMask__sw_g",
        "c_wSPMask__sfw_g",
    ]


def test_build_weapons_fills_skin_fields_by_guid(fake_catalog) -> None:
    weapons = _build_weapons(_WEAPON_VALUES, {"AB-12": [_FAKE_GUID, _WEAPON_SKIN_GUID]})
    assert weapons[0].skin_name == "普鲁士人"
    assert weapons[0].skin_rarity == "Superior"
    assert weapons[0].skin_image is not None
    assert weapons[0].skin_image.startswith("https://eaassets-a.akamaihd.net/")
    # 没装皮肤 / 无 guid 的条目三字段为 None
    for w in weapons[1:]:
        assert (w.skin_name, w.skin_rarity, w.skin_image) == (None, None, None)


def test_build_vehicles_maps_catalog_fields(fake_catalog) -> None:
    vehicles = _build_vehicles(_VEHICLE_VALUES, {})
    assert [v.name for v in vehicles] == ["A7V 重型坦克", "L 级驱逐舰", "哈尔伯施塔特 CL.II 攻击机"]
    a7v = vehicles[0]
    assert a7v.category == "重型坦克"
    assert a7v.kills == 800
    assert a7v.destroyed == 60
    assert a7v.time_seconds == 7200
    assert a7v.image == (
        "https://eaassets-a.akamaihd.net/battlelog/battlebinary/gamedata/Tunguska/3/4/A7V-456.png"
    )
    assert vehicles[1].destroyed is None


def test_build_vehicles_fills_skin_by_kit_number(fake_catalog) -> None:
    vehicles = _build_vehicles(
        _VEHICLE_VALUES,
        {"17": [_VEHICLE_SKIN_GUID], "23": [_FAKE_GUID, _VEHICLE_SKIN_GUID]},
    )
    # 重型坦克：sortOrder 5 -> kit 17
    assert vehicles[0].skin_name == "M1917 奖杯 (极稀有)"
    assert vehicles[0].skin_rarity == "Superior"
    # 驱逐舰：sortOrder 14 撞号，按分类名 -> kit 23
    assert vehicles[1].skin_name == "M1917 奖杯 (极稀有)"
    # 攻擊機：无 kit 映射，不展示皮肤
    assert vehicles[2].skin_name is None
    assert vehicles[2].skin_rarity is None
    assert vehicles[2].skin_image is None
