/**
 * 战地 1 百科（游戏里的 Codex）：310 条，2026-10 从 Companion 一次性导出，见 tools/bf1-codex。
 *
 * 列表只带短字段；正文（约 300KB）单独成 JSON：详情页在服务端读，列表页搜索或展开阅读时再按需加载。
 * 图片随前端发布在 public/bf1/codex 下，640 宽原图和 480 宽列表图两档，比例都是 640:901。
 */

import entries from "./data/codex.json";

export type CodexCategory = "武器" | "载具" | "战略" | "战争" | "全世界";

export interface CodexEntry {
  /** 游戏内编号，如 c003、cxp113，也是详情页路由段 */
  code: string;
  category: CodexCategory;
  /** 仅武器类有：冲锋枪、轻机枪……（由解锁条件里的武器代号推出） */
  weaponClass: string;
  /** 资料片代号，本体为空串 */
  expansion: string;
  name: string;
  header: string;
  subHeader: string;
  /** 解锁条件，如「用 MP18 冲锋枪进行 10 次击杀」 */
  unlock: string;
}

export const CODEX_ENTRIES = entries as CodexEntry[];

export const CODEX_CATEGORIES: CodexCategory[] = ["武器", "载具", "战略", "战争", "全世界"];

export const WEAPON_CLASSES = [
  "冲锋枪",
  "轻机枪",
  "半自动步枪",
  "栓动步枪",
  "霰弹枪",
  "手枪",
  "手枪卡宾枪",
  "近战",
  "配备",
  "精英兵",
  "定点武器",
  "骑兵",
];

export const EXPANSIONS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "", label: "本体" },
  { key: "XPACK1", label: "誓死坚守" },
  { key: "XPACK2", label: "以沙皇之名" },
  { key: "XPACK3", label: "力挽狂澜" },
  { key: "XPACK4", label: "启示录" },
];

const EXPANSION_LABEL = Object.fromEntries(EXPANSIONS.map((x) => [x.key, x.label]));

export function expansionLabel(key: string): string {
  return EXPANSION_LABEL[key] ?? key;
}

/** 卡片角标 / 详情页的分类行：「武器 · 冲锋枪」 */
export function codexKind(e: CodexEntry): string {
  return e.weaponClass ? `${e.category} · ${e.weaponClass}` : e.category;
}

export const CODEX_IMAGE_WIDTH = 640;
export const CODEX_IMAGE_HEIGHT = 901;

export function codexImage(code: string, width: 640 | 480 = 640): string {
  return width === 480 ? `/bf1/codex/entries-480/${code}.webp` : `/bf1/codex/entries/${code}.webp`;
}

export function codexSrcSet(code: string): string {
  return `${codexImage(code, 480)} 480w, ${codexImage(code)} 640w`;
}

const BY_CODE = new Map(CODEX_ENTRIES.map((e, i) => [e.code, i]));

export function getCodexEntry(code: string): CodexEntry | undefined {
  const i = BY_CODE.get(code);
  return i == null ? undefined : CODEX_ENTRIES[i];
}

/** 游戏内顺序里的前后条目，详情页翻页用 */
export function codexNeighbors(code: string): { prev?: CodexEntry; next?: CodexEntry } {
  const i = BY_CODE.get(code);
  if (i == null) return {};
  return { prev: CODEX_ENTRIES[i - 1], next: CODEX_ENTRIES[i + 1] };
}

/** 同类条目：武器按枪械类别，其余按大类；不含自身 */
export function codexRelated(e: CodexEntry, limit = 8): CodexEntry[] {
  const same = CODEX_ENTRIES.filter(
    (x) =>
      x.code !== e.code &&
      x.category === e.category &&
      (!e.weaponClass || x.weaponClass === e.weaponClass),
  );
  // 从自身位置往后取，看起来像「接着读」，不足再从头补
  const at = same.findIndex((x) => (BY_CODE.get(x.code) ?? 0) > (BY_CODE.get(e.code) ?? 0));
  const ordered = at < 0 ? same : [...same.slice(at), ...same.slice(0, at)];
  return ordered.slice(0, limit);
}

let textsPromise: Promise<Record<string, string>> | null = null;

/** 浏览器端按需加载全部正文；打包成单独的 chunk，首屏不下载 */
export function loadCodexTexts(): Promise<Record<string, string>> {
  textsPromise ??= import("./data/codex-text.json").then(
    (m) => m.default as Record<string, string>,
  );
  return textsPromise;
}

/** 列表筛选状态在地址栏里的写法，详情页的面包屑也用它生成回列表的链接 */
export function codexListHref(filter: { cat?: string; wc?: string } = {}): string {
  const u = new URLSearchParams();
  if (filter.cat) u.set("cat", filter.cat);
  if (filter.wc) u.set("wc", filter.wc);
  const qs = u.toString();
  return qs ? `/bf1/codex?${qs}` : "/bf1/codex";
}

/** 复制正文时附带的纯文本格式：标题、分类、解锁条件、正文、出处 */
export function codexPlainText(e: CodexEntry, body: string, link: string): string {
  const head = [`【${e.name}】${e.header !== e.name ? e.header : ""}`.trim()];
  if (e.subHeader) head.push(e.subHeader);
  head.push(`${codexKind(e)} · ${e.code}`, `解锁：${e.unlock}`);
  return `${head.join("\n")}\n\n${body}\n\n—— 战地 1 百科 · ${link}`;
}
