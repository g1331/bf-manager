"""BF1 服务器查询服务的纯函数单测

覆盖 _to_summary / _to_rotation / _to_extras 三个不依赖 EA 网络与数据库的纯转换函数，
以及 ServerLifecycle 的时间戳 validator 边界。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.bf1.server import ServerLifecycle
from app.services.bf1.server_service import _to_extras, _to_rotation, _to_summary


def _make_search_item() -> dict:
    """模拟 searchServers 返回的单条 gameservers 数据"""
    return {
        "serverId": 12345,
        "gameId": 99999,
        "persistedGameId": "abc-def",
        "name": "Test Server",
        "mapName": "MP_Alps",
        "mapMode": "Conquest",
        "region": "Asia",
        "serverType": "RANKED",
        "ranked": True,
        "hasPassword": False,
        "description": "hello",
        "slots": {
            "Soldier": {"current": 42, "max": 64},
            "Queue": {"current": 3, "max": 10},
            "Spectator": {"current": 1, "max": 4},
        },
        "mapImageUrl": "[BB_PREFIX]/gamedata/Tunguska/X/Y/MP_Alps_Large.jpg",
    }


def test_to_summary_translates_map_mode_region_and_normalizes_image() -> None:
    summary = _to_summary(_make_search_item())
    assert summary.map_name == "MP_Alps"
    assert summary.map_display_name == "剃刀边缘"
    assert summary.game_mode == "Conquest"
    assert summary.mode_display_name == "征服"
    assert summary.region == "Asia"
    assert summary.region_display_name == "亚洲"
    assert summary.map_image_url == (
        "https://eaassets-a.akamaihd.net/battlelog/battlebinary"
        "/gamedata/Tunguska/X/Y/MP_Alps_Large.jpg"
    )
    assert summary.player_count == 42
    assert summary.max_player_count == 64
    assert summary.queue_count == 3


def test_to_summary_official_flag_from_server_type() -> None:
    """官服判定取 serverType == "OFFICIAL"，EA 返回项不含 official 字段"""
    raw = _make_search_item()
    raw["serverType"] = "OFFICIAL"
    assert _to_summary(raw).is_official is True

    raw["serverType"] = "RANKED"
    assert _to_summary(raw).is_official is False

    # 缺 serverType 时即便残留 official=True，也不据此判官服（避免回退到已废弃字段）
    raw.pop("serverType", None)
    raw["official"] = True
    assert _to_summary(raw).is_official is False


def test_to_summary_extracts_country_and_tick_rate() -> None:
    """搜索/详情项透传 country 与 tickRate；country 为空字符串时降为 None"""
    raw = _make_search_item()
    raw["country"] = "JP"
    raw["tickRate"] = 60
    raw["pingSiteAlias"] = "nrt"
    summary = _to_summary(raw)
    assert summary.country == "JP"
    assert summary.tick_rate == 60
    assert summary.ping_site == "nrt"

    # 缺 pingSiteAlias 时降为 None
    raw.pop("pingSiteAlias", None)
    assert _to_summary(raw).ping_site is None

    # 官服常返回空 country，统一降为 None（前端「有值才渲染国旗」）
    raw["country"] = ""
    assert _to_summary(raw).country is None

    # tickRate 缺失或非数值时降为 None，不抛异常
    raw.pop("tickRate", None)
    assert _to_summary(raw).tick_rate is None
    raw["tickRate"] = "bad"
    assert _to_summary(raw).tick_rate is None


def test_to_summary_with_unknown_map_falls_back_to_raw_code() -> None:
    raw = _make_search_item()
    raw["mapName"] = "MP_FutureDLC_Q"
    summary = _to_summary(raw)
    assert summary.map_name == "MP_FutureDLC_Q"
    assert summary.map_display_name == "MP_FutureDLC_Q"


def test_to_summary_keeps_original_fields_when_translation_missing() -> None:
    raw = _make_search_item()
    raw["region"] = "Mars"
    raw["mapMode"] = "WeirdMode"
    summary = _to_summary(raw)
    assert summary.region == "Mars"
    assert summary.region_display_name == "Mars"
    assert summary.game_mode == "WeirdMode"
    assert summary.mode_display_name == "WeirdMode"


def test_to_rotation_marks_current_by_map_code_not_pretty_name() -> None:
    """rotation `is_current` 必须用 mapName 代号比较，不能被 prettyName 误判"""
    raw = {
        "serverInfo": {
            "mapName": "MP_Alps",
            "mapNamePretty": "剃刀边缘",
        },
        "rotation": [
            {
                "mapName": "MP_Forest",
                "mapPrettyName": "阿尔贡森林",
                "modeName": "Conquest",
                "mapImage": "[BB_PREFIX]/a.jpg",
            },
            {
                "mapName": "MP_Alps",
                "mapPrettyName": "剃刀边缘",
                "modeName": "Conquest",
                "mapImage": "[BB_PREFIX]/b.jpg",
            },
        ],
    }
    rotation = _to_rotation(raw)
    assert [r.is_current for r in rotation] == [False, True]
    assert rotation[1].map_display_name == "剃刀边缘"
    assert rotation[1].mode_display_name == "征服"
    assert rotation[0].map_image_url == (
        "https://eaassets-a.akamaihd.net/battlelog/battlebinary/a.jpg"
    )


def test_to_rotation_returns_no_current_when_server_map_code_missing() -> None:
    """serverInfo.mapName 缺失时，不应把任何 rotation 项标 current（即使 item.mapName 也为 None）"""
    raw = {
        "serverInfo": {},
        "rotation": [
            {"mapName": None, "mapPrettyName": "X"},
            {"mapName": "MP_Forest"},
        ],
    }
    rotation = _to_rotation(raw)
    assert all(r.is_current is False for r in rotation)


def test_to_rotation_empty_when_raw_has_no_rotation() -> None:
    assert _to_rotation({}) == []
    assert _to_rotation({"serverInfo": {}}) == []


def _make_full_detail() -> dict:
    """模拟 getFullServerDetails(gameId).result 的典型结构"""
    return {
        "serverInfo": {
            "name": "FULL Server",
            "gameId": "8460032230118",
            "guid": "1a9f5032-0cc0-4c0a-a83b-f229463ea39e",
            "serverBookmarkCount": "123",
            "mapName": "MP_Alps",
            "mapMode": "Conquest",
            "region": "Asia",
            "serverType": "OFFICIAL",
            "slots": {
                "Soldier": {"current": 42, "max": 64},
                "Queue": {"current": 0, "max": 10},
                "Spectator": {"current": 0, "max": 4},
            },
            "settings": {"customGame": False},
        },
        "rspInfo": {
            "owner": {
                "personaId": "1005880910785",
                "displayName": "B_bili33",
                "avatar": "https://avatar.example/a.png",
                "platform": "pc",
                "platformId": "1011592110785",
                "nucleusId": "1011592110785",
                "accountId": "0",  # 历史占位字段，service 不暴露，留在 fixture 验证不会泄漏到 schema
            },
            "server": {
                "serverId": "10667817",
                "createdDate": "1708228215000",
                "expirationDate": "1739764215000",
                "updatedDate": "1738228215000",
            },
            "adminList": [
                {
                    "personaId": "1001",
                    "displayName": "AdminOne",
                    "avatar": "https://avatar.example/1.png",
                    "platform": "pc",
                    "platformId": "1101",
                    "nucleusId": "1101",
                    "accountId": "0",
                },
                {"personaId": "1002", "displayName": "AdminTwo"},
                {"personaId": None, "displayName": "Broken"},
            ],
            "vipList": [
                {"personaId": "2001", "displayName": "VipOne"},
            ],
            "bannedList": [
                {
                    "personaId": "9001",
                    "displayName": "BannedOne",
                    "avatar": "https://avatar.example/b1.png",
                    "platform": "pc",
                    "platformId": "9101",
                    "nucleusId": "9101",
                },
                {"personaId": "9002", "displayName": "BannedTwo"},
                {"personaId": "not-a-number", "displayName": "Garbage"},
            ],
        },
        "platoonInfo": {
            "tag": "ABC",
            "name": "Alpha Bravo",
            "size": "20",
            "description": "战队简介",
            "emblem": (
                "https://eaassets-a.akamaihd.net/battlelog/bf-emblems"
                "/prod_default/exclusive/[SIZE]/EA.[FORMAT]"
            ),
        },
    }


def test_to_summary_official_flag_from_nested_server_info() -> None:
    """详情接口（getFullServerDetails.result）官服判定取嵌套 serverInfo.serverType"""
    raw = _make_full_detail()
    assert _to_summary(raw).is_official is True

    raw["serverInfo"]["serverType"] = "RANKED"
    assert _to_summary(raw).is_official is False

    # serverInfo 缺 serverType 时降为非官方，详情接口偶发缺字段不应误判官服
    del raw["serverInfo"]["serverType"]
    assert _to_summary(raw).is_official is False


def test_to_extras_full_payload() -> None:
    extras = _to_extras(_make_full_detail())
    assert extras.game_id == 8460032230118
    assert extras.server_id == 10667817
    assert extras.persisted_game_id == "1a9f5032-0cc0-4c0a-a83b-f229463ea39e"
    assert extras.bookmark_count == 123
    assert extras.owner is not None
    assert extras.owner.persona_id == 1005880910785
    assert extras.owner.display_name == "B_bili33"
    assert extras.owner.avatar_url == "https://avatar.example/a.png"
    assert extras.owner.platform == "pc"
    assert extras.owner.platform_id == "1011592110785"
    assert extras.owner.nucleus_id == "1011592110785"
    assert not hasattr(extras.owner, "account_id")
    assert extras.lifecycle.created_at == datetime.fromtimestamp(1708228215, tz=UTC)
    assert extras.lifecycle.expires_at == datetime.fromtimestamp(1739764215, tz=UTC)
    assert extras.lifecycle.updated_at == datetime.fromtimestamp(1738228215, tz=UTC)
    assert [a.persona_id for a in extras.admins] == [1001, 1002]
    assert extras.admins[0].avatar_url == "https://avatar.example/1.png"
    assert extras.admins[0].platform == "pc"
    assert extras.admins[0].platform_id == "1101"
    assert extras.admins[0].nucleus_id == "1101"
    assert not hasattr(extras.admins[0], "account_id")
    assert [v.persona_id for v in extras.vips] == [2001]
    assert [b.persona_id for b in extras.banned] == [9001, 9002]
    assert extras.banned[0].avatar_url == "https://avatar.example/b1.png"
    assert extras.banned[0].platform == "pc"
    assert extras.platoon is not None
    assert extras.platoon.tag == "ABC"
    assert extras.platoon.size == 20
    assert extras.platoon.emblem_url == (
        "https://eaassets-a.akamaihd.net/battlelog/bf-emblems/prod_default/exclusive/512/EA.png"
    )


def test_to_extras_without_rsp_and_platoon() -> None:
    """无 rspInfo / platoonInfo 时，只能从 serverInfo 回填 game_id / persisted_game_id / 收藏数"""
    raw = {
        "serverInfo": {
            "gameId": "999",
            "guid": "guid-xyz",
            "serverBookmarkCount": "0",
        }
    }
    extras = _to_extras(raw)
    assert extras.game_id == 999
    assert extras.server_id is None
    assert extras.persisted_game_id == "guid-xyz"
    assert extras.bookmark_count == 0
    assert extras.owner is None
    assert extras.lifecycle.created_at is None
    assert extras.lifecycle.expires_at is None
    assert extras.lifecycle.updated_at is None
    assert extras.admins == []
    assert extras.vips == []
    assert extras.banned == []
    assert extras.platoon is None


def test_to_extras_drops_admin_with_invalid_persona_id() -> None:
    raw = _make_full_detail()
    raw["rspInfo"]["adminList"] = [
        {"personaId": "not-a-number", "displayName": "X"},
        {"personaId": "", "displayName": "Y"},
        {"personaId": 0, "displayName": "Z"},
        {"personaId": "3003", "displayName": "Valid"},
    ]
    extras = _to_extras(raw)
    assert [a.persona_id for a in extras.admins] == [3003]


def test_server_lifecycle_validator_handles_garbage() -> None:
    """非法时间戳（空 / 非数值 / None）必须降为 None，而不是抛异常"""
    lc = ServerLifecycle(created_at="", expires_at="not-a-ts", updated_at=None)  # type: ignore[arg-type]
    assert lc.created_at is None
    assert lc.expires_at is None
    assert lc.updated_at is None


def test_server_lifecycle_validator_accepts_integer_ms() -> None:
    lc = ServerLifecycle(created_at=1708228215000)  # type: ignore[arg-type]
    assert lc.created_at == datetime.fromtimestamp(1708228215, tz=UTC)
