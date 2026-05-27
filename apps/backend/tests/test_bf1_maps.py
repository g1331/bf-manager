"""BF1 地图 / 模式 / 地区翻译与图片 URL 规范化单测"""

from __future__ import annotations

import logging

from app.domain.games.bf1.maps import (
    _warned_unknown_maps,
    _warned_unknown_modes,
    _warned_unknown_regions,
    normalize_map_image_url,
    translate_map_name,
    translate_mode_name,
    translate_region,
)


def _reset_warn_caches() -> None:
    """每条用例独立验证 warn-once，避免上一条用例污染"""
    _warned_unknown_maps.clear()
    _warned_unknown_modes.clear()
    _warned_unknown_regions.clear()


def test_translate_map_name_known_code_returns_chinese() -> None:
    assert translate_map_name("MP_Alps") == "剃刀边缘"
    assert translate_map_name("MP_MountainFort") == "格拉巴山"


def test_translate_map_name_unknown_falls_back_and_warns(
    caplog: logging.LogCaptureFixture,
) -> None:
    _reset_warn_caches()
    with caplog.at_level(logging.WARNING):
        result = translate_map_name("MP_FutureDLC_X")
    assert result == "MP_FutureDLC_X"
    assert any("MP_FutureDLC_X" in record.message for record in caplog.records)


def test_translate_map_name_unknown_warns_only_once(
    caplog: logging.LogCaptureFixture,
) -> None:
    _reset_warn_caches()
    with caplog.at_level(logging.WARNING):
        translate_map_name("MP_RepeatDLC_X")
        translate_map_name("MP_RepeatDLC_X")
        translate_map_name("MP_RepeatDLC_X")
    matched = [r for r in caplog.records if "MP_RepeatDLC_X" in r.message]
    assert len(matched) == 1


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
