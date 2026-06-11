"""BF1 皮肤静态表查询单测

覆盖 lookup_skin 的命中 / 未命中 / 大小写归一，以及数据文件随包发布的完整性。
"""

from __future__ import annotations

from app.domain.games.bf1.skins import _load_skins, lookup_skin

# 皮肤静态表中的真实条目
_KNOWN_GUID = "6E5FDF7A-B920-4728-8019-056A4AEE130E"  # M1917 獎盃 (極稀有)


def test_lookup_skin_hit_expands_image_url() -> None:
    skin = lookup_skin(_KNOWN_GUID)
    assert skin is not None
    assert skin["name"] == "M1917 獎盃 (極稀有)"
    assert skin["rarity"] == "Superior"
    # image 占位符已展开为完整 CDN URL
    assert skin["image"] is not None
    assert skin["image"].startswith("https://eaassets-a.akamaihd.net/battlelog/battlebinary/")
    assert "[BB_PREFIX]" not in skin["image"]


def test_lookup_skin_is_case_insensitive() -> None:
    assert lookup_skin(_KNOWN_GUID.lower()) is not None


def test_lookup_skin_miss_returns_none() -> None:
    # preset 槽位中混有非皮肤物件 guid，未命中属预期
    assert lookup_skin("00000000-0000-0000-0000-000000000000") is None
    assert lookup_skin(None) is None
    assert lookup_skin("") is None


def test_skin_table_ships_with_package() -> None:
    # 数据文件缺失会静默降级为全员无皮肤，这里兜底确保表随包存在且规模正常
    table = _load_skins()
    assert len(table) > 800
