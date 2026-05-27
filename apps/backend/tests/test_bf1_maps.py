"""BF1 地图 / 模式 / 地区翻译与图片 URL 规范化单测"""

from __future__ import annotations

import logging

from app.domain.games.bf1.maps import (
    MapData,
    normalize_map_image_url,
    translate_map_name,
    translate_mode_name,
    translate_region,
)


def test_translate_map_name_known_code_returns_chinese() -> None:
    assert translate_map_name("MP_Alps") == "剃刀边缘"
    assert (
        translate_map_name("MP_MountainFort") == MapData.MapTeamDict["MP_MountainFort"]["Chinese"]
    )


def test_translate_map_name_unknown_falls_back_and_warns(
    caplog: logging.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = translate_map_name("MP_FutureDLC_X")
    assert result == "MP_FutureDLC_X"
    assert any("MP_FutureDLC_X" in record.message for record in caplog.records)


def test_translate_map_name_none() -> None:
    assert translate_map_name(None) is None
    assert translate_map_name("") is None


def test_translate_mode_name_known_and_unknown(
    caplog: logging.LogCaptureFixture,
) -> None:
    assert translate_mode_name("Conquest") == "征服"
    with caplog.at_level(logging.WARNING):
        assert translate_mode_name("UnknownMode") == "UnknownMode"


def test_translate_region_known_and_unknown(
    caplog: logging.LogCaptureFixture,
) -> None:
    assert translate_region("Asia") == "亚洲"
    assert translate_region("NAm") == "北美"
    assert translate_region("AC") == "南极洲"
    with caplog.at_level(logging.WARNING):
        assert translate_region("Mars") == "Mars"


def test_normalize_map_image_url_expands_bb_prefix() -> None:
    raw = "[BB_PREFIX]/gamedata/Tunguska/33/69/MP_Forest_LandscapeLarge-dfbbe910.jpg"
    expected = (
        "https://eaassets-a.akamaihd.net/battlelog/battlebinary"
        "/gamedata/Tunguska/33/69/MP_Forest_LandscapeLarge-dfbbe910.jpg"
    )
    assert normalize_map_image_url(raw) == expected


def test_normalize_map_image_url_passes_absolute_url_through() -> None:
    raw = "https://cdn.example.com/foo.jpg"
    assert normalize_map_image_url(raw) == raw


def test_normalize_map_image_url_none() -> None:
    assert normalize_map_image_url(None) is None
    assert normalize_map_image_url("") is None
