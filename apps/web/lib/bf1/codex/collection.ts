/**
 * 图鉴里百科以外的收藏品：勋章、狗牌、勋带、勤务小任务。与百科同一批导出，见 tools/bf1-codex。
 * 分类顺序沿用游戏内的顺序（即导出数据里首次出现的顺序）。
 */

import assignmentsJson from "./data/assignments.json";
import dogtagsJson from "./data/dogtags.json";
import medalsJson from "./data/medals.json";
import ribbonsJson from "./data/ribbons.json";

export interface Medal {
  code: string;
  category: string;
  expansion: string;
  name: string;
  description: string;
  score: number;
  stages: Array<{ name: string; score: number }>;
  /** 奖励狗牌的 id */
  dogtags: string[];
}

export interface Dogtag {
  id: string;
  category: string;
  /** 基本狗牌挂在正面，高级狗牌挂在背面 */
  side: "front" | "back";
  expansion: string;
  name: string;
  description: string;
  /** 游戏内排序 */
  index: number;
}

export interface Ribbon {
  code: string;
  category: string;
  expansion: string;
  name: string;
  description: string;
  score: number;
}

export interface Assignment {
  code: string;
  group: string;
  name: string;
  /** 解锁前置的说明，如「完成 3 个初来乍到小任务以开始」，第一组为空 */
  description: string;
  criteria: string[];
  /** 前置任务的 code */
  requires: string[];
  image: string;
}

export const MEDALS = medalsJson as Medal[];
export const DOGTAGS = dogtagsJson as Dogtag[];
export const RIBBONS = ribbonsJson as Ribbon[];
export const ASSIGNMENTS = assignmentsJson as Assignment[];

/** 按首次出现的顺序分组 */
export function groupBy<T>(items: T[], key: (x: T) => string): Array<{ key: string; items: T[] }> {
  const map = new Map<string, T[]>();
  for (const x of items) {
    const k = key(x);
    const list = map.get(k);
    if (list) list.push(x);
    else map.set(k, [x]);
  }
  return [...map].map(([k, list]) => ({ key: k, items: list }));
}

export const DOGTAG_CATEGORIES = [...new Set(DOGTAGS.map((t) => t.category))];

export const DOGTAG_SIDE_LABEL: Record<Dogtag["side"], string> = {
  front: "基本狗牌",
  back: "高级狗牌",
};

export const medalImage = (code: string) => `/bf1/codex/medals/${code}.webp`;
export const dogtagImage = (id: string) => `/bf1/codex/dogtags/${id}.webp`;
export const ribbonImage = (code: string) => `/bf1/codex/ribbons/${code}.webp`;
export const assignmentImage = (image: string) => `/bf1/codex/assignments/${image}.webp`;

const MEDAL_BY_CODE = new Map(MEDALS.map((m) => [m.code, m]));
const DOGTAG_BY_ID = new Map(DOGTAGS.map((t) => [t.id, t]));
const ASSIGNMENT_BY_CODE = new Map(ASSIGNMENTS.map((a) => [a.code, a]));
/** 狗牌 → 奖励它的勋章 */
const MEDAL_BY_DOGTAG = new Map(MEDALS.flatMap((m) => m.dogtags.map((id) => [id, m] as const)));

export const getMedal = (code: string) => MEDAL_BY_CODE.get(code);
export const getDogtag = (id: string) => DOGTAG_BY_ID.get(id);
export const getAssignment = (code: string) => ASSIGNMENT_BY_CODE.get(code);
export const medalOfDogtag = (id: string) => MEDAL_BY_DOGTAG.get(id);

/** 同一分类、同一面里按游戏内顺序的前后两枚；「进度」类连起来是一段短篇故事，跨正反面按 index 读 */
export function dogtagNeighbors(tag: Dogtag): { prev?: Dogtag; next?: Dogtag } {
  const same = DOGTAGS.filter(
    (t) => t.category === tag.category && (tag.category === "进度" || t.side === tag.side),
  ).sort((a, b) => a.index - b.index);
  const i = same.findIndex((t) => t.id === tag.id);
  return { prev: same[i - 1], next: same[i + 1] };
}

export function medalNeighbors(code: string): { prev?: Medal; next?: Medal } {
  const i = MEDALS.findIndex((m) => m.code === code);
  return { prev: MEDALS[i - 1], next: MEDALS[i + 1] };
}

export function medalPlainText(m: Medal, link: string): string {
  const stages = m.stages.map((s, i) => `${i + 1}. ${s.name}`).join("\n");
  return `【${m.name}】${m.category}勋章\n${m.description}\n\n阶段任务：\n${stages}\n\n—— 战地 1 勋章 · ${link}`;
}

export function dogtagPlainText(t: Dogtag, link: string): string {
  return `【${t.name}】${t.category} · ${DOGTAG_SIDE_LABEL[t.side]}\n${t.description}\n\n—— 战地 1 狗牌 · ${link}`;
}
