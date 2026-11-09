"""网页与公开 API 共用的 BF6 图鉴，图片由 web 的 public/bf6 提供。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, TypeAdapter

Section = Literal[
    "weapons",
    "weapon_categories",
    "vehicles",
    "vehicle_categories",
    "gadgets",
    "kits",
    "modes",
    "maps",
]


class CatalogItem(BaseModel):
    name: str | None = None
    zh: str | None = None
    en: str | None = None
    img: bool = False
    art: bool = False
    art_fallback: str | None = None


# vehicle_types 是网页用于细分载具的标签，其余分区都是按 ID 查询的条目。
_data = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
_catalog = TypeAdapter(dict[str, dict[str, CatalogItem]]).validate_python(
    {section: items for section, items in _data.items() if section != "vehicle_types"}
)


def metadata(section: Section, item_id: str) -> tuple[str | None, str | None]:
    item = _catalog[section].get(item_id)
    if item is None:
        return None, None
    name = item.zh or item.name or item.en
    image = None
    if item.img:
        image = f"/bf6/{section}/{item_id}.webp"
    elif section == "kits":
        image = f"/bf6/classes/{item_id}-wide.webp"
    elif section == "modes":
        art = item_id if item.art else item.art_fallback
        if art:
            image = f"/bf6/mode-art/{art}.webp"
    return name, image
