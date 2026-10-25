"""玩家列表的管理 / VIP / 阵营取自 Blaze roster ATTR，不再调 getFullServerDetails。"""

from __future__ import annotations

from app.domain.games.bf1.maps import MapData
from app.services.bf1.blaze_service import _attr_ids, _faction_map, _operation_progress


def test_attr_ids_joins_slices_cut_mid_number():
    # 长串按长度切片，切口落在 1006801751459 中间
    attrs = {"admins1": "386703378;10068017", "admins2": "51459;902727040;", "admins3": ""}
    assert _attr_ids(attrs, "admins") == {386703378, 1006801751459, 902727040}


def test_attr_ids_empty_or_missing():
    assert _attr_ids({}, "vips") == set()
    assert _attr_ids({"vips1": "", "vips2": "", "vips3": "", "vips4": ""}, "vips") == set()


def test_faction_map_from_level():
    entry = MapData.MapTeamDict["MP_Amiens"]
    assert _faction_map("MP_Amiens") == {0: entry["Team1"], 1: entry["Team2"]}


def test_faction_map_unknown_map_falls_back():
    assert _faction_map("MP_NoSuchMap") == {}
    assert _faction_map(None) == {}


def test_operation_progress_multi_map():
    op = _operation_progress({"mode": "BreakthroughLarge", "level": "MP_Amiens", "progress": "3"})
    assert op is not None
    assert op.maps == ["圣康坦的伤痕", "亚眠"]
    assert (op.map_index, op.sectors_taken) == (1, 3)


def test_operation_progress_single_map_and_non_operation():
    op = _operation_progress(
        {"mode": "BreakthroughLarge", "level": "MP_Offensive", "progress": "0"}
    )
    assert op is not None and op.maps == ["索姆河"] and op.map_index == 0
    assert _operation_progress({"mode": "Conquest", "level": "MP_Amiens", "progress": "1"}) is None
    assert _operation_progress({"mode": "BreakthroughLarge", "level": "MP_Amiens"}) is None
