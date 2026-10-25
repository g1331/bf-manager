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

    # 地图封面（Gateway mapImageUrl 原值）。Blaze 快照不带图片 URL，文件名含哈希无法拼出，
    # 只能固化：2026-10-25 从 searchServers / getFullServerDetails 采集。
    # shortcut: MP_Bridge / Ravines / Valley / Alps / Blitz / London 当时无服在跑未采到，
    # 这几张图在快照路径下无封面；采到后补进来即可。
    MapImageDict = {
        "MP_Amiens": "[BB_PREFIX]/gamedata/Tunguska/31/107/MP_Amiens_LandscapeLarge-e195589d.jpg",
        "MP_Beachhead": "[BB_PREFIX]/gamedata/Tunguska/90/19/MP_Beachhead_LandscapeLarge-5a13c655.jpg",
        "MP_Chateau": "[BB_PREFIX]/gamedata/Tunguska/36/77/MP_Chateau_LandscapeLarge-244d5987.jpg",
        "MP_Desert": "[BB_PREFIX]/gamedata/Tunguska/40/9/MP_Desert_LandscapeLarge-d8f749da.jpg",
        "MP_FaoFortress": "[BB_PREFIX]/gamedata/Tunguska/54/47/MP_FaoFortress_LandscapeLarge-cad1748e.jpg",
        "MP_Fields": "[BB_PREFIX]/gamedata/Tunguska/95/83/MP_Fields_LandscapeLarge-5f53ddc4.jpg",
        "MP_Forest": "[BB_PREFIX]/gamedata/Tunguska/33/69/MP_Forest_LandscapeLarge-dfbbe910.jpg",
        "MP_Giant": "[BB_PREFIX]/gamedata/Tunguska/35/11/MP_Giant_LandscapeLarge-dd0b93ef.jpg",
        "MP_Graveyard": "[BB_PREFIX]/gamedata/Tunguska/67/16/MP_Graveyard_LandscapeLarge-bd1012e6.jpg",
        "MP_Harbor": "[BB_PREFIX]/gamedata/Tunguska/45/126/MP_Harbor_LandscapeLarge-d382c7ea.jpg",
        "MP_Hell": "[BB_PREFIX]/gamedata/Tunguska/113/118/MP_Hell_LandscapeLarge-7176911c.jpg",
        "MP_Islands": "[BB_PREFIX]/gamedata/Tunguska/55/40/MP_Islands_LandscapeLarge-c9d8272b.jpg",
        "MP_ItalianCoast": "[BB_PREFIX]/gamedata/Tunguska/21/3/MP_ItalianCoast_LandscapeLarge-1503eec7.jpg",
        "MP_MountainFort": "[BB_PREFIX]/gamedata/Tunguska/118/81/MP_MountainFort_LandscapeLarge-8a517533.jpg",
        "MP_Naval": "[BB_PREFIX]/gamedata/Tunguska/36/46/MP_Naval_LandscapeLarge-dc2e8daf.jpg",
        "MP_Offensive": "[BB_PREFIX]/gamedata/Tunguska/109/85/MP_Offensive_LandscapeLarge-6dabdea3.jpg",
        "MP_Ridge": "[BB_PREFIX]/gamedata/Tunguska/116/5/MP_Ridge_LandscapeLarge-8c057a19.jpg",
        "MP_River": "[BB_PREFIX]/gamedata/Tunguska/33/68/MP_River_LandscapeLarge-21443ae9.jpg",
        "MP_Scar": "[BB_PREFIX]/gamedata/Tunguska/18/37/MP_Scar_LandscapeLarge-ee25fbd6.jpg",
        "MP_ShovelTown": "[BB_PREFIX]/gamedata/Tunguska/48/86/MP_Shoveltown_LandscapeLarge-d0aa5920.jpg",
        "MP_Suez": "[BB_PREFIX]/gamedata/Tunguska/10/48/MP_Suez_LandscapeLarge-f630fc76.jpg",
        "MP_Trench": "[BB_PREFIX]/gamedata/Tunguska/37/47/MP_Trench_LandscapeLarge-dbd1248f.jpg",
        "MP_Tsaritsyn": "[BB_PREFIX]/gamedata/Tunguska/45/67/MP_Tsaritsyn_LandscapeLarge-2dbd3bf5.jpg",
        "MP_Underworld": "[BB_PREFIX]/gamedata/Tunguska/74/59/MP_Underworld_LandscapeLarge-b6c5c7e7.jpg",
        "MP_Verdun": "[BB_PREFIX]/gamedata/Tunguska/26/54/MP_Verdun_LandscapeLarge-1a364063.jpg",
        "MP_Volga": "[BB_PREFIX]/gamedata/Tunguska/106/60/MP_Volga_LandscapeLarge-6ac49c25.jpg",
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

# 每个未知代号在进程生命周期内只 warn 一次，避免高频接口刷屏。
_warned_unknown_maps: set[str] = set()
_warned_unknown_modes: set[str] = set()
_warned_unknown_regions: set[str] = set()


def _warn_once(seen: set[str], code: str, kind: str) -> None:
    if code in seen:
        return
    seen.add(code)
    logger.warning("BF1 %s代号无中文映射: %s", kind, code)


def translate_map_name(raw: str | None) -> str | None:
    """把 `MP_*` 内部代号翻译为中文地图名；命中失败回退原值并 warn 一次"""
    if not raw:
        return None
    entry = MapData.MapTeamDict.get(raw)
    if entry is None:
        _warn_once(_warned_unknown_maps, raw, "地图")
        return raw
    return entry["Chinese"]


def translate_mode_name(raw: str | None) -> str | None:
    """把英文模式代号翻译为中文模式名；命中失败回退原值并 warn 一次"""
    if not raw:
        return None
    mapped = MapData.ModeDict.get(raw)
    if mapped is None:
        _warn_once(_warned_unknown_modes, raw, "模式")
        return raw
    return mapped


def translate_region(raw: str | None) -> str | None:
    """把上游地区代号翻译为中文；命中失败回退原值并 warn 一次"""
    if not raw:
        return None
    mapped = MapData.RegionDict.get(raw)
    if mapped is None:
        _warn_once(_warned_unknown_regions, raw, "地区")
        return raw
    return mapped


def normalize_map_image_url(raw: str | None) -> str | None:
    """把上游 `[BB_PREFIX]/...` 占位符 URL 展开为 EA CDN 完整 URL"""
    if not raw:
        return None
    if raw.startswith(_BB_PREFIX):
        return _BB_CDN + raw[len(_BB_PREFIX) :]
    return raw


def normalize_emblem_url(raw: str | None) -> str | None:
    """把战队徽章 URL 中的 `[SIZE]` / `[FORMAT]` 占位符替换为可加载的实际取值。

    EA 战队 emblem URL 有两种形态：官方徽章 `.../exclusive/[SIZE]/EA.[FORMAT]`、
    自定义徽章 `.../ugc/.../[SIZE].[FORMAT]?v=...`，两者都带 `[SIZE]`/`[FORMAT]`
    占位符。统一取 512 尺寸与 png 格式（EA CDN 支持的常见组合），无占位符的 URL
    原样返回。空值返回 None。
    """
    if not raw:
        return None
    return raw.replace("[SIZE]", "512").replace("[FORMAT]", "png")
