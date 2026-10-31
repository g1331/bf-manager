"""BF1 Blaze 武器目录的分类核对

目录的分类沿用 Gateway，Gateway 自己有分错的（三八式（巡逻）在「佩枪」等），生成工具用
CATEGORY_FIXES 校正。这里按 Blaze 英文标签推出每件武器该在哪一类，重新生成目录后能马上发现新的错分。
"""

from app.domain.games.bf1.blaze_catalog import catalog

# 精英兵（战场装备）的专属武器
_ELITE = {
    "Special - Flamethrower",
    "Special - Martini Henry GL",
    "Special - Maxim MG",
    "Special - Tankgewehr",
    "Special - Villar Perosa",
    "Special - Flare Gun Signal",
}
# 投掷物槽位里的爆炸物；其余 Explosives（炸药、地雷、绊雷、反坦克手榴弹、十字弓…）是配备
_GRENADES = {
    "Explosives - Frag Grenade",
    "Explosives - Gas Grenade",
    "Explosives - Impact Grenade",
    "Explosives - Improvised Grenade",
    "Explosives - Incendiary Grenade",
    "Explosives - Light AT Grenade",
    "Explosives - Offensive Grenade",
    "Explosives - Smoke Grenade",
    # 步枪手榴弹在游戏里是医疗兵的配备，EA 的生涯武器列表把它放在手榴弹里，沿用
    "Explosives - Rifle Frag",
    "Explosives - Rifle HE",
    "Explosives - Rifle Smoke",
}


def _expected(label: str) -> str:
    if label.startswith("Rifle - Single - "):
        return "制式步枪" if label.endswith("Standard Issue") else "步枪"
    if label.startswith("Rifle - Semi - "):
        return "半自动步枪"
    if label.startswith("MG - LMG - "):
        return "轻机枪"
    if label.startswith("MG - SMG - "):
        return "冲锋枪"
    if label.startswith("Handgun - "):
        return "佩枪"
    # 坦克兵 / 飞行员的武器：手枪卡宾枪和短管霰弹枪
    if label.startswith("Pistol Carbine - ") or label == "Shotgun - Sawed Off Shotgun":
        return "坦克/驾驶员"
    if label.startswith("Shotgun - "):
        return "霰弹枪"
    if label.startswith("Melee - "):
        return "近战武器"
    if label in _ELITE:
        return "战场装备"
    if label in _GRENADES:
        return "手榴弹"
    if label.startswith(("Special - ", "Explosives - ", "Equipment - ")) or label == (
        "Livens Projector"
    ):
        return "配备"
    raise AssertionError(f"没有分类规则的标签：{label}，在测试里补上")


def test_weapon_categories_follow_blaze_labels() -> None:
    wrong = [
        (code, e["name"], e["category"], _expected(e["label"]))
        for code, e in catalog("weapons").items()
        if e.get("label") and e["category"] != _expected(e["label"])
    ]
    assert wrong == []


def test_patrol_variants_are_in_their_class_category() -> None:
    weapons = catalog("weapons")
    assert weapons["wRSinAriP"]["category"] == "步枪"  # 三八式步枪（巡逻）
    assert weapons["wRSinCarP"]["category"] == "步枪"  # 卡尔卡诺 M91 卡宾枪（巡逻）
    assert weapons["wSMGMauP"]["category"] == "冲锋枪"  # M1917 卡宾枪（巡逻）


def test_unlabeled_entries_are_gadgets_or_grenades() -> None:
    """Blaze 没有单项统计的配备（绷带包等）和俄罗斯标准手榴弹没有标签，分类只可能是这两类"""
    for e in catalog("weapons").values():
        if not e.get("label"):
            assert e["category"] in {"配备", "手榴弹"}, e["name"]
