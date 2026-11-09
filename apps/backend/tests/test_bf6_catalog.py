"""共享图鉴的展示字段与网页静态资源一致。"""

import json
from pathlib import Path

import pytest
from app.domain.games.bf6 import catalog
from app.services.bf6.stats_normalizer import VEHICLE_CATEGORIES, WEAPON_CATEGORIES


@pytest.mark.parametrize(
    ("section", "item_id", "expected"),
    [
        ("weapons", "mg_l110", ("L110", "/bf6/weapons/mg_l110.webp")),
        ("weapons", "unknown", (None, None)),
        ("vehicles", "air_uh06", ("UH-06", None)),
        ("gadgets", "c4", ("C-4 炸药", "/bf6/gadgets/c4.webp")),
        ("modes", "op", ("Operations", None)),
        ("modes", "cq", ("征服", "/bf6/mode-art/cq.webp")),
        ("modes", "graniteDuo", ("大逃杀 · 双人", "/bf6/mode-art/granite.webp")),
        ("modes", "carrier", ("航母突击", None)),
        ("kits", "assault", ("突击兵", "/bf6/classes/assault-wide.webp")),
    ],
)
def test_metadata(section: catalog.Section, item_id: str, expected) -> None:
    assert catalog.metadata(section, item_id) == expected


def test_catalog_categories_cover_normalized_stats() -> None:
    data = json.loads(Path(catalog.__file__).with_suffix(".json").read_text())
    assert set(data["weapon_categories"]) == WEAPON_CATEGORIES
    assert set(data["vehicle_categories"]) == VEHICLE_CATEGORIES


def test_catalog_images_exist_in_web() -> None:
    public = Path(__file__).resolve().parents[2] / "web" / "public"
    for section, items in catalog._catalog.items():
        for item_id in items:
            name, image = catalog.metadata(section, item_id)
            assert name, (section, item_id)
            if image is not None:
                assert image.startswith("/bf6/")
                assert (public / image.lstrip("/")).is_file(), image


def test_mode_images_are_always_artwork() -> None:
    for item_id in catalog._catalog["modes"]:
        _, image = catalog.metadata("modes", item_id)
        assert image is None or image.startswith("/bf6/mode-art/"), item_id
