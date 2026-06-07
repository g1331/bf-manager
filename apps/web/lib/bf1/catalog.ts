/**
 * BF1 固定目录：游戏模式、地图、地区的完整候选集（代号 → 简体名）。
 *
 * BF1 是已完结游戏，模式与地图集合稳定不再变化，故作为筛选候选的固定全集，
 * 不从已加载的服务器数据派生——否则搜索前无选项、搜索后也只剩结果里出现过的项。
 * 数据与后端 `app/domain/games/bf1/maps.py` 的 ModeDict / MapTeamDict / RegionDict 对齐，
 * 代号即接口里的 `game_mode` / `map_name` / `region` 取值，用于按代号筛选。
 */

export interface CatalogEntry {
  code: string;
  label: string;
}

const MODE_DICT: Record<string, string> = {
  Rush: "突袭",
  Conquest: "征服",
  TeamDeathMatch: "团队死斗",
  Breakthrough: "闪击行动",
  Domination: "抢攻",
  Possession: "战争信鸽",
  BreakthroughLarge: "行动模式",
  TugOfWar: "前线",
  ZoneControl: "空降补给",
  AirAssault: "空中突击",
};

const MAP_DICT: Record<string, string> = {
  MP_MountainFort: "格拉巴山",
  MP_Forest: "阿尔贡森林",
  MP_ItalianCoast: "帝国边境",
  MP_Chateau: "流血宴厅",
  MP_Scar: "圣康坦的伤痕",
  MP_Desert: "西奈沙漠",
  MP_Amiens: "亚眠",
  MP_Suez: "苏伊士",
  MP_FaoFortress: "法欧堡",
  MP_Giant: "庞然暗影",
  MP_Fields: "苏瓦松",
  MP_Graveyard: "决裂",
  MP_Underworld: "法乌克斯要塞",
  MP_Verdun: "凡尔登高地",
  MP_Trench: "尼维尔之夜",
  MP_ShovelTown: "攻占托尔",
  MP_Bridge: "勃鲁希洛夫关口",
  MP_Islands: "阿尔比恩",
  MP_Ravines: "武普库夫山口",
  MP_Valley: "加利西亚",
  MP_Tsaritsyn: "察里津",
  MP_Volga: "窝瓦河",
  MP_Beachhead: "海丽丝岬",
  MP_Harbor: "泽布吕赫",
  MP_Naval: "黑尔戈兰湾",
  MP_Ridge: "阿奇巴巴",
  MP_Offensive: "索姆河",
  MP_Hell: "帕斯尚尔",
  MP_River: "卡波雷托",
  MP_Alps: "剃刀边缘",
  MP_Blitz: "伦敦的呼唤：夜袭",
  MP_London: "伦敦的呼唤：灾祸",
};

const REGION_DICT: Record<string, string> = {
  Asia: "亚洲",
  NAm: "北美",
  SAm: "南美",
  EU: "欧洲",
  OC: "大洋洲",
  Afr: "非洲",
  AC: "南极洲",
};

function toSortedEntries(dict: Record<string, string>): CatalogEntry[] {
  return Object.entries(dict)
    .map(([code, label]) => ({ code, label }))
    .sort((a, b) => a.label.localeCompare(b.label, "zh-Hans"));
}

export const BF1_MODES: CatalogEntry[] = toSortedEntries(MODE_DICT);
export const BF1_MAPS: CatalogEntry[] = toSortedEntries(MAP_DICT);
export const BF1_REGIONS: CatalogEntry[] = toSortedEntries(REGION_DICT);

export function modeLabel(code: string): string {
  return MODE_DICT[code] ?? code;
}
export function mapLabel(code: string): string {
  return MAP_DICT[code] ?? code;
}
export function regionLabel(code: string): string {
  return REGION_DICT[code] ?? code;
}
