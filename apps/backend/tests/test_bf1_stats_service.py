"""BF1 战绩提取的纯函数单测

覆盖 _build_summary（生涯综合）与 _build_soldiers（兵种分布）从 EA
detailedStats result 字典的提取逻辑：基础值（basicStats）、战斗细分项
（result 顶层）、载具/步战击杀拆分、最佳兵种、兵种分布，以及各类缺失降级。
字段名取自 EA 该接口的真实返回。
"""

from __future__ import annotations

from app.domain.games.bf1.maps import normalize_emblem_url
from app.services.bf1.stats_service import (
    _build_platoon,
    _build_soldiers,
    _build_summary,
    _parse_online,
)


def _make_result() -> dict:
    """模拟 EA detailedStatsByPersonaId 返回的 result 字典（截取关键字段）"""
    return {
        "basicStats": {
            "timePlayed": 1_200_000,
            "wins": 980,
            "losses": 540,
            "kills": 35_000,
            "deaths": 12_000,
            "kpm": 1.85,
            "spm": 720.0,
            "skill": 418.0,
            "rank": None,
        },
        # 战斗细分项在 result 顶层
        "killAssists": 4_800.0,
        "revives": 2_100.0,
        "heals": 9_500.0,
        "repairs": 1_200.0,
        "dogtagsTaken": 320,
        "highestKillStreak": 32,
        "longestHeadShot": 412.0,
        "favoriteClass": "Medic",
        "vehicleStats": [
            {"killsAs": 4_000.0, "name": "Heavy Tank"},
            {"killsAs": 2_800.0, "name": "Fighter"},
        ],
        "kitStats": [
            {
                "kits": 1,
                "name": "Assault",
                "prettyName": "突擊兵",
                "kills": 8_000.0,
                "score": 1.2e6,
                "secondsAs": 220_000.0,
            },
            {
                "kits": 3,
                "name": "Medic",
                "prettyName": "醫療兵",
                "kills": 15_000.0,
                "score": 2.8e6,
                "secondsAs": 540_000.0,
            },
            {
                "kits": 4,
                "name": "Scout",
                "prettyName": "偵察兵",
                "kills": 4_000.0,
                "score": 7.2e5,
                "secondsAs": 180_000.0,
            },
        ],
    }


def test_build_summary_extracts_all_fields() -> None:
    s = _build_summary(901001001, _make_result())
    assert s.persona_id == 901001001
    assert s.kills == 35_000
    assert s.deaths == 12_000
    assert s.wins == 980
    assert s.losses == 540
    assert s.kd == 35_000 / 12_000
    assert s.kpm == 1.85
    assert s.sps == 720.0 / 60.0
    assert s.time_played_seconds == 1_200_000
    assert s.skill == 418.0
    # 载具击杀 = 4000 + 2800，步战击杀 = 35000 - 6800
    assert s.vehicle_kills == 6_800
    assert s.infantry_kills == 28_200
    # 战斗细分项来自 result 顶层
    assert s.assists == 4_800
    assert s.revives == 2_100
    assert s.heals == 9_500
    assert s.repairs == 1_200
    assert s.dogtags == 320
    assert s.max_killstreak == 32
    assert s.longest_headshot_meters == 412.0
    # 最佳兵种 favoriteClass 转小写
    assert s.best_class == "medic"


def test_build_summary_computes_rank_from_spm_when_ea_rank_missing() -> None:
    # EA rank 为 None 时由 spm * timePlayed / 60 推算，结果应为正整数等级
    s = _build_summary(1, _make_result())
    assert s.rank is not None
    assert s.rank > 0


def test_build_summary_leaves_kill_split_empty_without_vehicle_stats() -> None:
    raw = _make_result()
    del raw["vehicleStats"]
    s = _build_summary(1, raw)
    # 无 vehicleStats 时步战/载具击杀无法拆分，留空而非填 0
    assert s.infantry_kills is None
    assert s.vehicle_kills is None
    # 总击杀仍应正常
    assert s.kills == 35_000


def test_build_summary_handles_empty_result() -> None:
    s = _build_summary(42, {})
    assert s.persona_id == 42
    assert s.kills == 0
    assert s.deaths == 0
    assert s.kd is None  # deaths 为 0 时不计算 kd
    assert s.skill is None
    assert s.assists is None
    assert s.infantry_kills is None
    assert s.vehicle_kills is None
    assert s.longest_headshot_meters is None
    assert s.best_class is None


def test_build_summary_skill_zero_is_preserved() -> None:
    # skill 为 0 是合法值（新号），应保留 0.0 而非降为 None
    raw = _make_result()
    raw["basicStats"]["skill"] = 0
    s = _build_summary(1, raw)
    assert s.skill == 0.0


def test_build_soldiers_extracts_class_distribution() -> None:
    soldiers = _build_soldiers(_make_result())
    assert len(soldiers) == 3
    # 兵种代号转小写，序列化 key 为 "class"
    assert [s.class_name for s in soldiers] == ["assault", "medic", "scout"]
    medic = soldiers[1]
    assert medic.kills == 15_000
    assert medic.score == 2_800_000
    assert medic.time_seconds == 540_000
    # 序列化别名验证：JSON key 应为 "class"
    dumped = medic.model_dump(by_alias=True)
    assert dumped["class"] == "medic"
    assert "class_name" not in dumped


def test_build_soldiers_empty_without_kit_stats() -> None:
    raw = _make_result()
    del raw["kitStats"]
    assert _build_soldiers(raw) == []
    assert _build_soldiers({}) == []


def test_build_soldiers_skips_items_without_name() -> None:
    raw = {"kitStats": [{"kills": 100}, {"name": "", "kills": 50}, {"name": "Pilot", "kills": 30}]}
    soldiers = _build_soldiers(raw)
    assert [s.class_name for s in soldiers] == ["pilot"]


def test_parse_online_player_in_server() -> None:
    res = {"result": {"42": {"name": "TestServer #1", "gameId": "123"}}}
    s = _parse_online(res, 42)
    assert s.is_online is True
    assert s.server_name == "TestServer #1"


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
