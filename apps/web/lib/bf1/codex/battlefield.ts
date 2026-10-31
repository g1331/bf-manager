/**
 * 图鉴「战场」分区：模式、多人地图、战争故事、阵营，外加载入画面小贴士。
 * 数据来自 Gamedata.getGameData 与小标语，见 tools/bf1-codex。
 *
 * 地图名统一走 catalog 的 mapLabel，和服务器、对局页面叫法一致；
 * 战争故事的章节归属是手写表（build.py 的 STORIES），已对照可靠资料核对。
 */

import { mapLabel } from "@/lib/bf1/catalog";
import data from "./data/battlefield.json";
import tips from "./data/tips.json";

export interface GameMode {
  /** 游戏内代号，如 Conquest，也是详情页路由段 */
  id: string;
  name: string;
  header: string;
  body: string;
  /** 「在该模式赢得 1 场游戏」解锁的百科条目，没有为空串 */
  codex: string;
}

export interface MapInfo {
  /** 如 MP_Verdun */
  id: string;
  /** XPACK0–4，本体为空串 */
  expansion: string;
  /** 「在这张图赢得 1 场游戏」解锁的百科条目：这张图的历史背景 */
  codex: string;
}

export interface Chapter {
  id: string;
  name: string;
  /** 这一章里解锁的百科条目 */
  codex: string[];
}

export interface WarStory {
  id: string;
  name: string;
  en: string;
  kind: "prologue" | "story" | "epilogue";
  /** 完成整个故事解锁的百科条目，序章、尾声可能没有 */
  completion: string;
  chapters: Chapter[];
}

export interface Faction {
  id: string;
  name: string;
  short: string;
  codex: string;
}

export interface Tip {
  text: string;
  type: "map" | "mode";
  /** 地图或模式代号；模式类大多是不挂标签的通用贴士 */
  tags: string[];
}

export const MODES = data.modes as GameMode[];
export const MAPS = data.maps as MapInfo[];
export const STORIES = data.stories as WarStory[];
export const FACTIONS = data.factions as Faction[];
export const TIPS = tips as Tip[];

/** 地图按资料片分组的顺序；庞然暗影是一张单独发布的免费地图 */
export const MAP_EXPANSIONS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "", label: "本体" },
  { key: "XPACK0", label: "庞然暗影" },
  { key: "XPACK1", label: "誓死坚守" },
  { key: "XPACK2", label: "以沙皇之名" },
  { key: "XPACK3", label: "力挽狂澜" },
  { key: "XPACK4", label: "启示录" },
];

const MAP_EXPANSION_LABEL = Object.fromEntries(MAP_EXPANSIONS.map((x) => [x.key, x.label]));

export function mapExpansionLabel(key: string): string {
  return MAP_EXPANSION_LABEL[key] ?? key;
}

export function mapName(m: MapInfo): string {
  return mapLabel(m.id);
}

export function mapImage(id: string, width: 1000 | 480 = 1000): string {
  return width === 480 ? `/bf1/codex/maps-480/${id}.webp` : `/bf1/codex/maps/${id}.webp`;
}

export function modeImage(id: string, width: 1000 | 480 = 1000): string {
  return width === 480 ? `/bf1/codex/modes-480/${id}.webp` : `/bf1/codex/modes/${id}.webp`;
}

export function factionImage(id: string): string {
  return `/bf1/codex/factions/${id}.webp`;
}

export const getMap = (id: string) => MAPS.find((m) => m.id === id);
export const getMode = (id: string) => MODES.find((m) => m.id === id);

/** 按资料片顺序排好的地图，详情页翻页也按这个顺序 */
export const MAPS_ORDERED: MapInfo[] = MAP_EXPANSIONS.flatMap((x) =>
  MAPS.filter((m) => m.expansion === x.key),
);

export function mapNeighbors(id: string): { prev?: MapInfo; next?: MapInfo } {
  const i = MAPS_ORDERED.findIndex((m) => m.id === id);
  return { prev: MAPS_ORDERED[i - 1], next: MAPS_ORDERED[i + 1] };
}

export function modeNeighbors(id: string): { prev?: GameMode; next?: GameMode } {
  const i = MODES.findIndex((m) => m.id === id);
  return { prev: MODES[i - 1], next: MODES[i + 1] };
}

/** 挂在某张地图或某个模式上的载入贴士 */
export function tipsFor(tag: string): Tip[] {
  return TIPS.filter((t) => t.tags.includes(tag));
}

/** 不挂任何地图、模式的通用贴士（多是一战冷知识） */
export const GENERAL_TIPS = TIPS.filter((t) => t.tags.length === 0);
