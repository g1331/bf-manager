from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MapData:
    AHU = "奥匈帝国"
    GER = "德意志帝国"
    OTM = "奥斯曼帝国"
    ITA = "意大利王国"
    UK = "大英帝国"
    RM = "皇家海军陆战队"
    USA = "美国"
    FRA = "法国"
    RUS = "俄罗斯帝国"
    BOL = "红军"

    # 地图数据
    MapTeamDict = {
        "MP_MountainFort": {"Chinese": "格拉巴山", "Team1": ITA, "Team2": AHU},
        "MP_Forest": {"Chinese": "阿尔贡森林", "Team1": USA, "Team2": GER},
        "MP_ItalianCoast": {"Chinese": "帝国边境", "Team1": ITA, "Team2": AHU},
        "MP_Chateau": {"Chinese": "流血宴厅", "Team1": USA, "Team2": GER},
        "MP_Scar": {"Chinese": "圣康坦的伤痕", "Team1": GER, "Team2": UK},
        "MP_Desert": {"Chinese": "西奈沙漠", "Team1": UK, "Team2": OTM},
        "MP_Amiens": {"Chinese": "亚眠", "Team1": GER, "Team2": UK},
        "MP_Suez": {"Chinese": "苏伊士", "Team1": UK, "Team2": OTM},
        "MP_FaoFortress": {"Chinese": "法欧堡", "Team1": UK, "Team2": OTM},
        "MP_Giant": {"Chinese": "庞然暗影", "Team1": GER, "Team2": UK},
        "MP_Fields": {"Chinese": "苏瓦松", "Team1": FRA, "Team2": GER},
        "MP_Graveyard": {"Chinese": "决裂", "Team1": FRA, "Team2": GER},
        "MP_Underworld": {"Chinese": "法乌克斯要塞", "Team1": GER, "Team2": FRA},
        "MP_Verdun": {"Chinese": "凡尔登高地", "Team1": GER, "Team2": FRA},
        "MP_Trench": {"Chinese": "尼维尔之夜", "Team1": GER, "Team2": FRA},
        "MP_ShovelTown": {"Chinese": "攻占托尔", "Team1": GER, "Team2": FRA},
        "MP_Bridge": {"Chinese": "勃鲁希洛夫关口", "Team1": RUS, "Team2": AHU},
        "MP_Islands": {"Chinese": "阿尔比恩", "Team1": GER, "Team2": RUS},
        "MP_Ravines": {"Chinese": "武普库夫山口", "Team1": AHU, "Team2": RUS},
        "MP_Valley": {"Chinese": "加利西亚", "Team1": RUS, "Team2": AHU},
        "MP_Tsaritsyn": {"Chinese": "察里津", "Team1": BOL, "Team2": RUS},
        "MP_Volga": {"Chinese": "窝瓦河", "Team1": BOL, "Team2": RUS},
        "MP_Beachhead": {"Chinese": "海丽丝岬", "Team1": UK, "Team2": OTM},
        "MP_Harbor": {"Chinese": "泽布吕赫", "Team1": RM, "Team2": GER},
        "MP_Naval": {"Chinese": "黑尔戈兰湾", "Team1": RM, "Team2": GER},
        "MP_Ridge": {"Chinese": "阿奇巴巴", "Team1": UK, "Team2": OTM},
        "MP_Offensive": {"Chinese": "索姆河", "Team1": UK, "Team2": GER},
        "MP_Hell": {"Chinese": "帕斯尚尔", "Team1": UK, "Team2": GER},
        "MP_River": {"Chinese": "卡波雷托", "Team1": AHU, "Team2": ITA},
        "MP_Alps": {"Chinese": "剃刀边缘", "Team1": GER, "Team2": UK},
        "MP_Blitz": {"Chinese": "伦敦的呼唤：夜袭", "Team1": GER, "Team2": UK},
        "MP_London": {"Chinese": "伦敦的呼唤：灾祸", "Team1": GER, "Team2": UK},
    }

    ModeDict = {
        "Rush": "突袭",
        "Conquest": "征服",
        "TeamDeathMatch": "团队死斗",
        "Breakthrough": "闪击行动",
        "Domination": "抢攻",
        "Possession": "战争信鸽",
        "BreakthroughLarge": "行动模式",
        "TugOfWar": "前线",
        "ZoneControl": "空降补给",
        "AirAssault": "空中突击",
    }

    RegionDict = {
        "Asia": "亚洲",
        "NAm": "北美",
        "SAm": "南美",
        "EU": "欧洲",
        "OC": "大洋洲",
        "Afr": "非洲",
        "AC": "南极洲",
    }


_BB_PREFIX = "[BB_PREFIX]"
_BB_CDN = "https://eaassets-a.akamaihd.net/battlelog/battlebinary"


def translate_map_name(raw: str | None) -> str | None:
    """把 `MP_*` 内部代号翻译为中文地图名；命中失败回退原值并记录 warning"""
    if not raw:
        return None
    entry = MapData.MapTeamDict.get(raw)
    if entry is None:
        logger.warning("BF1 地图代号无中文映射: %s", raw)
        return raw
    return entry["Chinese"]


def translate_mode_name(raw: str | None) -> str | None:
    """把英文模式代号翻译为中文模式名；命中失败回退原值"""
    if not raw:
        return None
    mapped = MapData.ModeDict.get(raw)
    if mapped is None:
        logger.warning("BF1 模式代号无中文映射: %s", raw)
        return raw
    return mapped


def translate_region(raw: str | None) -> str | None:
    """把上游地区代号翻译为中文；命中失败回退原值"""
    if not raw:
        return None
    mapped = MapData.RegionDict.get(raw)
    if mapped is None:
        logger.warning("BF1 地区代号无中文映射: %s", raw)
        return raw
    return mapped


def normalize_map_image_url(raw: str | None) -> str | None:
    """把上游 `[BB_PREFIX]/...` 占位符 URL 展开为 EA CDN 完整 URL"""
    if not raw:
        return None
    if raw.startswith(_BB_PREFIX):
        return _BB_CDN + raw[len(_BB_PREFIX) :]
    return raw
