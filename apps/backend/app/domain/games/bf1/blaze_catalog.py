"""BF1 Blaze 武器 / 载具目录：Blaze 统计代号 → 名称 / 分类 / 图片 / GUID / 取数字段

数据文件 data/blaze_catalog.json 由 tools/export_bf1_blaze_catalog.py 生成：拿一批玩家，把每个
Blaze 代号的数值与 Gateway 武器 / 载具条目逐一对上，名称、分类、图片、GUID 沿用 Gateway；
Gateway 没有的条目（维和者、防毒面具等）在工具里手工补名，没有图片。每项的 ``cat`` / ``stats``
是取数用的 Blaze 类别与统计名，``order`` 是 Gateway 里的展示顺序。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent / "data" / "blaze_catalog.json"


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, dict[str, Any]]]:
    try:
        with _DATA_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"目录根节点应为 dict，实际 {type(data).__name__}")
        return data
    except (OSError, ValueError) as exc:
        logger.warning("BF1 Blaze 武器目录加载失败，武器 / 载具列表为空: %s", exc)
        return {}


def catalog(kind: str) -> dict[str, dict[str, Any]]:
    """kind 为 weapons 或 vehicles，返回 {代号: 条目}"""
    return _load().get(kind) or {}


def stat_names(kind: str) -> dict[str, list[str]]:
    """{Blaze 类别: 该类条目用到的全部统计名}，供 Stats.getStats 按类别批量取"""
    out: dict[str, list[str]] = {}
    for entry in catalog(kind).values():
        out.setdefault(entry["cat"], []).extend(entry["stats"].values())
    return out
