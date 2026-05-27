"""BF1 服务器查询服务的纯函数单测

只覆盖 _to_summary / _to_rotation 两个不依赖 EA 网络与数据库的纯转换函数。
"""

from __future__ import annotations

from app.services.bf1.server_service import _to_rotation, _to_summary


def _make_search_item() -> dict:
    """模拟 searchServers 返回的单条 gameservers 数据"""
    return {
        "serverId": 12345,
        "gameId": 99999,
        "persistedGameId": "abc-def",
        "name": "Test Server",
        "mapName": "MP_Alps",
        "mode": "Conquest",
        "region": "Asia",
        "official": False,
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


def test_to_summary_with_unknown_map_falls_back_to_raw_code() -> None:
    raw = _make_search_item()
    raw["mapName"] = "MP_FutureDLC_Q"
    summary = _to_summary(raw)
    assert summary.map_name == "MP_FutureDLC_Q"
    assert summary.map_display_name == "MP_FutureDLC_Q"


def test_to_summary_keeps_original_fields_when_translation_missing() -> None:
    raw = _make_search_item()
    raw["region"] = "Mars"
    raw["mode"] = "WeirdMode"
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
