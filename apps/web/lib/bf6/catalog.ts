/**
 * BF6 图鉴：把统计里的内部 ID（mg_l110、veh 的 air_panthera、lvl 的 mpaftermath……）翻成名称和图片。
 * 图片都托管在 public/bf6，图鉴里没有的条目回落到 ID 本身，不会空白。
 */
import {
  GADGETS,
  KITS,
  MAPS,
  MODES,
  VEHICLES,
  VEHICLE_TYPES,
  WEAPONS,
  WEAPON_CATEGORIES,
} from "./catalog-data";

export { KITS, WEAPON_CATEGORIES } from "./catalog-data";

export interface Bf6CatalogItem {
  name: string;
  /** 载具的英文分类，如 Air Combat */
  type?: string;
  /** public/bf6 下有没有这张图 */
  img?: boolean;
}

export interface Bf6MapInfo {
  zh: string;
  en: string;
  img?: boolean;
}

export interface Bf6ModeInfo {
  /** 没有核对过的官方中文名时为空，显示英文 */
  zh?: string;
  en: string;
  icon?: boolean;
  art?: boolean;
}

const BASE = "/bf6";

/* ------------------------------ 武器 ------------------------------ */

export type WeaponCategory = keyof typeof WEAPON_CATEGORIES;

export function weaponCategory(id: string): WeaponCategory | null {
  const prefix = id.split("_")[0];
  return prefix in WEAPON_CATEGORIES ? (prefix as WeaponCategory) : null;
}

export function weaponInfo(id: string) {
  const item = WEAPONS[id];
  const category = weaponCategory(id);
  return {
    name: item?.name ?? id,
    category,
    categoryZh: category ? WEAPON_CATEGORIES[category].zh : "其他",
    img: item?.img ? `${BASE}/weapons/${id}.webp` : null,
  };
}

/* ------------------------------ 载具 ------------------------------ */

/** 载具筛选分组：按 ID 前缀分空中 / 地面（含水面），图鉴里有水面分类的单独列出 */
export type VehicleGroup = "air" | "ground" | "naval";

export function vehicleInfo(id: string) {
  const item = VEHICLES[id];
  const naval = item?.type === "Naval Combat";
  const group: VehicleGroup = naval ? "naval" : id.startsWith("air_") ? "air" : "ground";
  return {
    name: item?.name ?? id,
    typeZh: item?.type ? (VEHICLE_TYPES[item.type] ?? item.type) : null,
    group,
    img: item?.img ? `${BASE}/vehicles/${id}.webp` : null,
  };
}

/* ------------------------------ 配备 ------------------------------ */

export const GADGET_GROUPS = {
  launcher: "发射器",
  explosive: "爆炸物",
  throwable: "投掷物",
  callin: "呼叫支援",
  other: "其他装备",
} as const;

export type GadgetGroup = keyof typeof GADGET_GROUPS;

function gadgetGroup(id: string): GadgetGroup {
  if (/^(rl|gl|il)_/.test(id)) return "launcher";
  if (id === "c4" || id.startsWith("mine_")) return "explosive";
  if (id.startsWith("gren_") || id === "tknife") return "throwable";
  if (id.startsWith("callin_")) return "callin";
  return "other";
}

export function gadgetInfo(id: string) {
  const item = GADGETS[id];
  return {
    name: item?.name ?? id,
    group: gadgetGroup(id),
    img: item?.img ? `${BASE}/gadgets/${id}.webp` : null,
  };
}

/* ------------------------------ 兵种 ------------------------------ */

export function kitInfo(id: string) {
  const kit = KITS[id];
  return {
    zh: kit?.zh ?? id,
    en: kit?.en ?? id,
    icon: kit ? `${BASE}/classes/${id}.svg` : null,
    wide: kit ? `${BASE}/classes/${id}-wide.webp` : null,
    tall: kit ? `${BASE}/classes/${id}-tall.webp` : null,
  };
}

/* ------------------------------ 地图 ------------------------------ */

export function mapInfo(id: string) {
  const item = MAPS[id];
  return {
    zh: item?.zh ?? id,
    en: item?.en ?? id,
    img: item?.img ? `${BASE}/maps/${id}.webp` : null,
    /** ftp 开头的是禁区冲突（大逃杀）地图 */
    redsec: id.startsWith("ftp"),
  };
}

/* ------------------------------ 模式 ------------------------------ */

export const MODE_GROUPS = [
  { key: "aow", zh: "全面战争", en: "All-Out Warfare", ids: ["cq", "bt", "esc", "rush"] },
  { key: "cqc", zh: "近距离战斗", en: "Close Quarters", ids: ["dom", "koth", "tdm", "sdm"] },
  {
    key: "redsec",
    zh: "禁区冲突",
    en: "REDSEC",
    ids: ["brsquad", "graniteDuo", "graniteSolo", "rr_solo", "gntgauntlet"],
  },
] as const;

const REDSEC_MODES = new Set<string>(MODE_GROUPS[2].ids);

export function modeInfo(id: string) {
  const item = MODES[id];
  const art = item?.art ? id : REDSEC_MODES.has(id) ? "granite" : null;
  return {
    /** 有官方中文名时为中文，否则为英文 */
    name: item?.zh ?? item?.en ?? id,
    en: item?.en ?? id,
    icon: item?.icon ? `${BASE}/modes/${id}.svg` : null,
    art: art ? `${BASE}/mode-art/${art}.webp` : null,
  };
}

/* ------------------------------ 统计图标 ------------------------------ */

/** 官网战绩页的统计图标（已改成主题橙色） */
export function statIcon(name: string): string {
  return `${BASE}/icons/${name}.svg`;
}

export const BF6_ASSETS = {
  redsecArt: `${BASE}/redsec.webp`,
  redsecLogo: `${BASE}/redsec-logo.webp`,
};
