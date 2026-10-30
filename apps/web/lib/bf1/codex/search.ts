/**
 * 百科的纯前端搜索：空格分隔的多个词必须同时命中；名称 > 解锁条件 > 正文。
 * 310 条、正文合计约 30 万字，每次按键全量扫一遍也在毫秒级，不需要建索引。
 */

import type { CodexEntry } from "./codex";

export function searchTerms(query: string): string[] {
  return query.trim().toLowerCase().split(/\s+/).filter(Boolean);
}

/** 命中返回分数，任一词没命中返回 -1。texts 还没加载完时只搜短字段 */
export function scoreEntry(e: CodexEntry, terms: string[], body?: string): number {
  const title = `${e.code} ${e.name} ${e.header} ${e.subHeader} ${e.weaponClass}`.toLowerCase();
  const unlock = e.unlock.toLowerCase();
  const text = body?.toLowerCase() ?? "";
  let score = 0;
  for (const t of terms) {
    const s =
      (title.includes(t) ? 10 : 0) + (unlock.includes(t) ? 4 : 0) + (text.includes(t) ? 1 : 0);
    if (!s) return -1;
    score += s;
  }
  return score;
}

/** 只在正文里命中的词，截一段上下文给卡片展示；标题已经命中的不重复给 */
export function bodySnippet(e: CodexEntry, terms: string[], body?: string): string {
  if (!body) return "";
  const title = `${e.code} ${e.name} ${e.header}`.toLowerCase();
  const low = body.toLowerCase();
  for (const t of terms) {
    if (title.includes(t)) continue;
    const k = low.indexOf(t);
    if (k < 0) continue;
    const from = Math.max(0, k - 16);
    const to = Math.min(body.length, k + t.length + 48);
    return `${from > 0 ? "…" : ""}${body.slice(from, to)}${to < body.length ? "…" : ""}`;
  }
  return "";
}

/** 按搜索词切段，奇数下标是命中的部分 */
export function splitByTerms(text: string, terms: string[]): string[] {
  if (!terms.length || !text) return [text];
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return text.split(new RegExp(`(${escaped.join("|")})`, "gi"));
}
