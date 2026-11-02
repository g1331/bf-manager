/**
 * 服务器浏览器的筛选状态：URL 参数与 localStorage 的读写、玩法开关规则与快捷标签的增减。
 *
 * 筛选条件同时写进 URL（可分享、刷新不丢）和 localStorage（下次打开沿用）。打开页面时
 * URL 里带了筛选就以 URL 为准，否则读 localStorage。读回来的值逐项按目录校验，过时或
 * 被手改的取值直接丢掉，免得把非法参数发给后端换来 422。
 */

import { BF1_MAPS, BF1_MODES, BF1_REGIONS } from "@/lib/bf1/catalog";

/** 开关取值 on / off，倍率取值是选项键（BD3） */
export type RuleValue = string;

export interface FilterState {
  modes: string[]; // game_mode 代号
  maps: string[]; // map_name 代号
  regions: string[]; // region 代号
  emptySlots: string[]; // EMPTY_SLOT_OPTIONS.id
  sizes: number[]; // max_player_count 档位
  serverTypes: string[]; // OFFICIAL / RANKED / PRIVATE
  rules: Record<string, RuleValue>; // 玩法规则，键形如 vehicles.L、scales.BD
  includeEmpty: boolean; // 含 0 人空服：全服快照不含空服，开启后后端改走 EA 抽样搜索
  nameFilter: string;
}

export const DEFAULT_FILTERS: FilterState = {
  modes: [],
  maps: [],
  regions: [],
  emptySlots: [],
  sizes: [],
  serverTypes: [],
  rules: {},
  includeEmpty: false,
  nameFilter: "",
};

/** 服务器规模（最大人数）固定档位，复刻游戏「遊戲規模」筛选项 */
export const SIZE_OPTIONS = [10, 16, 24, 32, 40, 48, 64];

/** 空位（剩余席位）分档，复刻游戏「空位」筛选项；id 与后端 slots 参数一致 */
export const EMPTY_SLOT_OPTIONS: { id: string; label: string }[] = [
  { id: "none", label: "无" },
  { id: "1-5", label: "1-5" },
  { id: "6-10", label: "6-10" },
  { id: "10+", label: "10+" },
];

export const SERVER_TYPE_IDS = ["OFFICIAL", "RANKED", "PRIVATE"];

const RULE_KEY = /^(vehicles|kits|weapons|misc|scales)\.[A-Za-z0-9]{1,8}$/;
const RULE_VALUE = /^(on|off|[A-Z]{2}[1-5])$/;

const MODE_CODES = new Set(BF1_MODES.map((m) => m.code));
const MAP_CODES = new Set(BF1_MAPS.map((m) => m.code));
const REGION_CODES = new Set(BF1_REGIONS.map((r) => r.code));
const SLOT_IDS = new Set(EMPTY_SLOT_OPTIONS.map((o) => o.id));

function pick(values: unknown, allowed: Set<string> | string[]): string[] {
  if (!Array.isArray(values)) return [];
  const ok = allowed instanceof Set ? allowed : new Set(allowed);
  return [...new Set(values.filter((v): v is string => typeof v === "string" && ok.has(v)))];
}

function pickRules(entries: [string, unknown][]): Record<string, RuleValue> {
  const out: Record<string, RuleValue> = {};
  for (const [key, value] of entries) {
    if (RULE_KEY.test(key) && typeof value === "string" && RULE_VALUE.test(value)) out[key] = value;
  }
  return out;
}

/** 把任意来源（localStorage 解析结果）收敛成合法的 FilterState */
export function sanitizeFilters(raw: unknown): FilterState {
  if (!raw || typeof raw !== "object") return DEFAULT_FILTERS;
  const r = raw as Record<string, unknown>;
  const sizes = Array.isArray(r.sizes)
    ? [...new Set(r.sizes.filter((n): n is number => SIZE_OPTIONS.includes(n as number)))]
    : [];
  const rules =
    r.rules && typeof r.rules === "object" ? pickRules(Object.entries(r.rules as object)) : {};
  return {
    modes: pick(r.modes, MODE_CODES),
    maps: pick(r.maps, MAP_CODES),
    regions: pick(r.regions, REGION_CODES),
    emptySlots: pick(r.emptySlots, SLOT_IDS),
    sizes,
    serverTypes: pick(r.serverTypes, SERVER_TYPE_IDS),
    rules,
    includeEmpty: r.includeEmpty === true,
    nameFilter: typeof r.nameFilter === "string" ? r.nameFilter.slice(0, 64) : "",
  };
}

/** 规则按键排序后转成接口参数 vehicles.L:off，顺序固定才能共用查询缓存 */
export function rulesToParams(rules: Record<string, RuleValue>): string[] {
  return Object.keys(rules)
    .sort()
    .map((k) => `${k}:${rules[k]}`);
}

// URL 参数名：短一点，分享链接不至于太长
const URL_KEYS = ["mode", "map", "region", "slots", "size", "type", "rule", "empty", "q"];

export function filtersToSearch(f: FilterState): string {
  const p = new URLSearchParams();
  f.modes.forEach((v) => p.append("mode", v));
  f.maps.forEach((v) => p.append("map", v));
  f.regions.forEach((v) => p.append("region", v));
  f.emptySlots.forEach((v) => p.append("slots", v));
  f.sizes.forEach((v) => p.append("size", String(v)));
  f.serverTypes.forEach((v) => p.append("type", v));
  rulesToParams(f.rules).forEach((v) => p.append("rule", v));
  if (f.includeEmpty) p.set("empty", "1");
  if (f.nameFilter.trim()) p.set("q", f.nameFilter.trim());
  return p.toString();
}

/** URL 里没有任何筛选参数时返回 null，交给 localStorage */
export function filtersFromSearch(search: string): FilterState | null {
  const p = new URLSearchParams(search);
  if (!URL_KEYS.some((k) => p.has(k))) return null;
  return sanitizeFilters({
    modes: p.getAll("mode"),
    maps: p.getAll("map"),
    regions: p.getAll("region"),
    emptySlots: p.getAll("slots"),
    sizes: p.getAll("size").map(Number),
    serverTypes: p.getAll("type"),
    rules: Object.fromEntries(
      p.getAll("rule").map((r) => {
        const i = r.lastIndexOf(":");
        return [r.slice(0, i), r.slice(i + 1)];
      }),
    ),
    includeEmpty: p.get("empty") === "1",
    nameFilter: p.get("q") ?? "",
  });
}

const STORAGE_KEY = "bf1-server-filters";

export function loadStoredFilters(): FilterState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? sanitizeFilters(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

export function storeFilters(f: FilterState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(f));
  } catch {
    // 隐私模式或配额满时放弃持久化，不影响筛选本身
  }
}

/** 快捷标签的规则是否都已生效 */
export function presetActive(
  rules: Record<string, RuleValue>,
  preset: Record<string, RuleValue>,
): boolean {
  return Object.entries(preset).every(([k, v]) => rules[k] === v);
}

/** 点快捷标签：已生效就撤掉它的规则，否则叠加上去（同一开关以标签为准） */
export function togglePreset(
  rules: Record<string, RuleValue>,
  preset: Record<string, RuleValue>,
): Record<string, RuleValue> {
  if (presetActive(rules, preset)) {
    const next = { ...rules };
    for (const k of Object.keys(preset)) delete next[k];
    return next;
  }
  return { ...rules, ...preset };
}

/** 设置单条规则；value 为 null 即「不限」 */
export function setRule(
  rules: Record<string, RuleValue>,
  key: string,
  value: RuleValue | null,
): Record<string, RuleValue> {
  const next = { ...rules };
  if (value === null) delete next[key];
  else next[key] = value;
  return next;
}
