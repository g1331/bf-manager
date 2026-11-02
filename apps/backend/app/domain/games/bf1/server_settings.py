"""BF1 服务器自定义设置：EA 繁体条目名 → 简体名 + 简体说明；没有 EA 设置时按快照掩码拼出同形设置

Gateway 按网关账号语言（zhtw）把 settings 各组的键译成繁体名，例如
``{"Scales": {"子彈傷害": "1.0"}}``。这里按繁体 name 在 gamedata.zh-TW.json
同组里找到条目，再用同组同 filterKey 的 gamedata.zh-CN.json 条目换成简体名与说明。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.games.bf1.server_filter_catalog import (
    SCALE_SETTINGS,
    SETTING_GROUPS,
    scale_state,
    toggle_state,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"


def _read_settings(locale: str) -> dict[str, list[dict[str, Any]]]:
    with (_DATA_DIR / f"gamedata.{locale}.json").open(encoding="utf-8") as f:
        settings: dict[str, list[dict[str, Any]]] = json.load(f)["settings"]
    return settings


@lru_cache(maxsize=1)
def _load_translations() -> dict[tuple[str, str], tuple[str, str]]:
    """(组名, 繁体名) → (简体名, 简体说明)；文件缺失或损坏时降级为空表（原样展示繁体）"""
    try:
        tw, cn = _read_settings("zh-TW"), _read_settings("zh-CN")
        table: dict[tuple[str, str], tuple[str, str]] = {}
        for group, tw_items in tw.items():
            cn_by_key = {item["filterKey"]: item for item in cn.get(group, [])}
            for item in tw_items:
                cn_item = cn_by_key.get(item["filterKey"])
                if cn_item:
                    table[(group, item["name"])] = (cn_item["name"], cn_item["description"])
        return table
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("BF1 设置翻译表加载失败，服务器设置保留繁体: %s", exc)
        return {}


def localize_settings(
    settings: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """返回 (键换成简体的 settings, 简体名 → 说明)；查不到的条目与非 dict 组原样保留"""
    table = _load_translations()
    localized: dict[str, Any] = {}
    descriptions: dict[str, str] = {}
    for group, entries in settings.items():
        if not isinstance(entries, dict):
            localized[group] = entries
            continue
        out: dict[str, Any] = {}
        for name, value in entries.items():
            hit = table.get((group, name))
            if hit:
                descriptions[hit[0]] = hit[1]
            out[hit[0] if hit else name] = value
        localized[group] = out
    return localized, descriptions


# 本站分组 id → gamedata 分组名
_MASK_GROUPS = {"vehicles": "Vehicles", "kits": "Kits", "weapons": "Weapons", "misc": "Misc"}


@lru_cache(maxsize=1)
def _load_cn_entries() -> dict[tuple[str, str], tuple[str, str]]:
    """(gamedata 分组, filterKey) → (简体名, 简体说明)；文件缺失或损坏时降级为空表"""
    try:
        return {
            (group, item["filterKey"]): (item["name"], item["description"])
            for group, items in _read_settings("zh-CN").items()
            for item in items
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("BF1 设置简体表加载失败: %s", exc)
        return {}


def settings_from_masks(masks: object) -> tuple[dict[str, Any], dict[str, str]]:
    """按快照掩码拼出与 localize_settings 同形的设置（简体名 → on/off 或倍率字符串）。

    官服的 EA 详情不带 settings，快照里却有掩码，用它补上。读不出来的组整组省略。
    """
    table = _load_cn_entries()
    settings: dict[str, Any] = {}
    descriptions: dict[str, str] = {}

    def put(group: str, key: str, fallback: str, value: str) -> None:
        name, desc = table.get((group, key), (fallback, ""))
        settings.setdefault(group, {})[name] = value
        if desc:
            descriptions[name] = desc

    for g in SETTING_GROUPS:
        for t in g.toggles:
            state = toggle_state(masks, t)
            if state is not None:
                put(_MASK_GROUPS[g.id], t.key, t.label, "on" if state else "off")
    for sc in SCALE_SETTINGS:
        option = scale_state(masks, sc)
        if option is not None:
            put("Scales", sc.name, sc.label, str(option.value))
    return settings, descriptions
