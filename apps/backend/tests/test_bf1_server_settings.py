"""BF1 服务器设置繁体 → 简体映射单测（用随包发布的真实 gamedata 数据）"""

from __future__ import annotations

from app.domain.games.bf1.server_settings import localize_settings


def test_localize_settings_translates_keys_and_collects_descriptions() -> None:
    settings, descriptions = localize_settings(
        {
            "Misc": {"擊殺鏡頭": "on", "友軍砲火": "off"},
            "Scales": {"子彈傷害": "1.0"},
            "Kits": {"支援兵": "on"},
        }
    )
    assert settings == {
        "Misc": {"击杀镜头": "on", "友军炮火": "off"},
        "Scales": {"子弹伤害": "1.0"},
        "Kits": {"支援兵": "on"},
    }
    assert descriptions["子弹伤害"] == "每颗子弹的伤害量。"
    assert set(descriptions) == {"击杀镜头", "友军炮火", "子弹伤害", "支援兵"}


def test_localize_settings_keeps_unknown_entries_and_groups() -> None:
    raw = {
        "Misc": {"未知設定": "on", "擊殺鏡頭": "off"},
        # 名称只在别的组存在时不跨组匹配
        "Weapons": {"擊殺鏡頭": "on"},
        "Unknown": {"某項": "1"},
        "Odd": "not-a-dict",
    }
    settings, descriptions = localize_settings(raw)
    assert settings == {
        "Misc": {"未知設定": "on", "击杀镜头": "off"},
        "Weapons": {"擊殺鏡頭": "on"},
        "Unknown": {"某項": "1"},
        "Odd": "not-a-dict",
    }
    assert set(descriptions) == {"击杀镜头"}
