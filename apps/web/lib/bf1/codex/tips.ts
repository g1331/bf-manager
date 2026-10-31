/**
 * 载入贴士的抽取规则（TipLine 与小贴士页共用）。只依赖传进来的数组，
 * 贴士数据由调用方按需动态加载，这个文件本身不会把 64KB 的 JSON 带进包里。
 */

import type { Tip } from "./battlefield";

/** 服务器上报的模式代号 → 贴士里用的标签；行动模式沿用闪击行动的贴士（区域、兵力规则相同） */
const MODE_TAG: Record<string, string> = { BreakthroughLarge: "Breakthrough" };

export function modeTag(mode: string): string {
  return MODE_TAG[mode] ?? mode;
}

export interface TipContext {
  map?: string | null;
  mode?: string | null;
}

/**
 * 有地图时先用这张图和当前模式的贴士；都没有就退到通用贴士。
 * 地图贴士少的图（个位数）也不掺通用贴士，保证说的是眼前这张图。
 */
export function tipPool(tips: Tip[], ctx: TipContext): Tip[] {
  const tags = [ctx.map, ctx.mode && modeTag(ctx.mode)].filter((t): t is string => !!t);
  if (tags.length) {
    const own = tips.filter((t) => t.tags.some((g) => tags.includes(g)));
    if (own.length) return own;
  }
  return tips.filter((t) => t.tags.length === 0);
}

/** 记住最近出现过的贴士，跨页面、跨会话避开短时间重复 */
const SEEN_KEY = "bf1:tips-seen";
const SEEN_LIMIT = 20;

export function readSeen(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(SEEN_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function markSeen(text: string): void {
  try {
    const next = [text, ...readSeen().filter((t) => t !== text)].slice(0, SEEN_LIMIT);
    localStorage.setItem(SEEN_KEY, JSON.stringify(next));
  } catch {
    // 隐私模式等写不进去时只是可能重复，不影响显示
  }
}

/** 从池子里随机挑一条：先避开最近看过的，池子太小全看过了，就只避开当前这条 */
export function pickTip(pool: Tip[], seen: string[], current?: string): Tip | undefined {
  const fresh = pool.filter((t) => t.text !== current && !seen.includes(t.text));
  const from = fresh.length ? fresh : pool.filter((t) => t.text !== current);
  const list = from.length ? from : pool;
  return list[Math.floor(Math.random() * list.length)];
}
