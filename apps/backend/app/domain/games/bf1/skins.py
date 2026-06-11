"""BF1 皮肤静态表：skin_guid → 名称 / 稀有度 / 图片

数据文件 data/skins.json 每条只含 name / rarity / image 三字段，键为大写 GUID，
image 保留 `[BB_PREFIX]` 占位符，查表时经 normalize_map_image_url 展开为完整 CDN URL。
玩家已装备皮肤的 guid 由 Loadout.getPresetsByPersonaId 给出，preset 槽位中混有
非皮肤物件的 guid，查不到即非皮肤，调用方按「取第一个命中项」处理。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from app.domain.games.bf1.maps import normalize_map_image_url

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent / "data" / "skins.json"


class SkinInfo(TypedDict):
    name: str | None
    rarity: str | None
    image: str | None


@lru_cache(maxsize=1)
def _load_skins() -> dict[str, dict[str, str | None]]:
    """懒加载皮肤表；文件缺失或损坏时降级为空表（全员无皮肤），不影响接口可用性"""
    try:
        with _DATA_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"皮肤表根节点应为 dict，实际 {type(data).__name__}")
        return data
    except (OSError, ValueError) as exc:
        logger.warning("BF1 皮肤表加载失败，皮肤展示降级: %s", exc)
        return {}


def lookup_skin(guid: str | None) -> SkinInfo | None:
    """按 GUID 查皮肤；大小写不敏感，未命中返回 None（preset 中混有非皮肤物件，属预期）"""
    if not guid:
        return None
    entry = _load_skins().get(guid.upper())
    if entry is None:
        return None
    return SkinInfo(
        name=entry.get("name"),
        rarity=entry.get("rarity"),
        image=normalize_map_image_url(entry.get("image")),
    )
