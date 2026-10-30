"use client";

import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { Search, X } from "lucide-react";
import { DarkInput } from "@/components/common/DarkInput";
import { usePageState } from "@/hooks/useNavigation";
import {
  CODEX_CATEGORIES,
  CODEX_ENTRIES,
  type CodexEntry,
  EXPANSIONS,
  loadCodexTexts,
  WEAPON_CLASSES,
} from "@/lib/bf1/codex/codex";
import { bodySnippet, scoreEntry, searchTerms } from "@/lib/bf1/codex/search";
import { cn } from "@/lib/utils";
import { CodexCard } from "./CodexCard";
import { CodexReader } from "./CodexReader";

type Density = "s" | "m" | "l";
type Sort = "game" | "name";

interface Filters {
  cat: string;
  wc: string;
  /** null 为不限；"" 是本体 */
  xp: string | null;
  sort: Sort;
}

const NO_FILTERS: Filters = { cat: "", wc: "", xp: null, sort: "game" };

const DENSITY: Record<Density, { label: string; grid: string; sizes: string }> = {
  s: {
    label: "小",
    grid: "grid-cols-3 gap-x-2.5 gap-y-4 sm:grid-cols-[repeat(auto-fill,minmax(128px,1fr))] sm:gap-x-4 sm:gap-y-6",
    sizes: "(min-width: 640px) 160px, 31vw",
  },
  m: {
    label: "中",
    grid: "grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(176px,1fr))] sm:gap-x-5 sm:gap-y-8",
    sizes: "(min-width: 640px) 220px, 46vw",
  },
  l: {
    label: "大",
    grid: "grid-cols-1 gap-y-8 min-[440px]:grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(240px,1fr))] sm:gap-x-6 sm:gap-y-10",
    sizes: "(min-width: 640px) 300px, 92vw",
  },
};

const DENSITY_KEY = "bfm:codex-density";
const densityListeners = new Set<() => void>();
function readDensity(): Density {
  const v = localStorage.getItem(DENSITY_KEY);
  return v === "s" || v === "l" ? v : "m";
}
function writeDensity(v: Density) {
  localStorage.setItem(DENSITY_KEY, v);
  densityListeners.forEach((l) => l());
}

/** 筛选和打开的条目都写进地址栏，链接发出去能还原同一个视图 */
function buildSearch(q: string, f: Filters, entry: string | null): string {
  const u = new URLSearchParams();
  if (q.trim()) u.set("q", q.trim());
  if (f.cat) u.set("cat", f.cat);
  if (f.wc) u.set("wc", f.wc);
  if (f.xp != null) u.set("xp", f.xp || "base");
  if (f.sort !== "game") u.set("sort", f.sort);
  if (entry) u.set("entry", entry);
  const s = u.toString();
  return `${window.location.pathname}${s ? `?${s}` : ""}`;
}

/**
 * 百科列表：搜索、按类别 / 枪械 / 资料片筛选、三档卡片密度，点卡片在列表上打开阅读层。
 *
 * 静态导出时按默认状态渲染完整的 310 张卡片；挂载后再读地址栏里的筛选和 ?entry=，
 * 所以分享出去的链接能还原视图，静态 HTML 也不用等脚本就能看到全部条目。
 * 打开阅读层会压一条历史记录，手机上按返回键关闭阅读层而不是离开页面。
 */
export function CodexBrowser() {
  const [query, setQuery] = usePageState("codex:q", "");
  const [filters, setFilters] = usePageState<Filters>("codex:filters", NO_FILTERS);
  const openCode = useSyncExternalStore(subscribeEntry, readEntry, () => null);
  const [texts, setTexts] = useState<Record<string, string>>();
  const density = useSyncExternalStore(
    (l) => {
      densityListeners.add(l);
      return () => densityListeners.delete(l);
    },
    readDensity,
    () => "m" as Density,
  );
  const ready = useRef(false);
  const pushed = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(false);

  // 搜索栏吸顶后才铺底色：停在原位时和页头融为一体，滚动起来再和卡片分开
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    // 手机端顶栏 48px；桌面端滚动容器在顶栏下方，哨兵被容器裁掉同样算离开
    const io = new IntersectionObserver(([e]) => setStuck(!e.isIntersecting), {
      rootMargin: "-48px 0px 0px 0px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const deferredQuery = useDeferredValue(query);
  const terms = useMemo(() => searchTerms(deferredQuery), [deferredQuery]);

  const wantTexts = useCallback(() => {
    if (!texts) void loadCodexTexts().then(setTexts);
  }, [texts]);

  // 挂载后读一次地址栏
  useEffect(() => {
    const u = new URLSearchParams(window.location.search);
    if (["q", "cat", "wc", "xp", "sort"].some((k) => u.has(k))) {
      const xp = u.get("xp");
      setQuery(u.get("q") ?? "");
      setFilters({
        cat: u.get("cat") ?? "",
        wc: u.get("wc") ?? "",
        xp: xp == null ? null : xp === "base" ? "" : xp,
        sort: u.get("sort") === "name" ? "name" : "game",
      });
    }
    ready.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在挂载时读一次
  }, []);

  // 筛选变化同步回地址栏（不产生历史记录）
  useEffect(() => {
    if (!ready.current) return;
    const t = setTimeout(
      () => window.history.replaceState(null, "", buildSearch(query, filters, openCode)),
      250,
    );
    return () => clearTimeout(t);
  }, [query, filters, openCode]);

  useEffect(() => {
    if (deferredQuery.trim() || openCode) wantTexts();
  }, [deferredQuery, openCode, wantTexts]);

  // 「/」聚焦搜索框
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.key !== "/" || openCode || el.closest("input, textarea, [contenteditable]")) return;
      e.preventDefault();
      input.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openCode]);

  // 每组筛选的计数按「其它条件不变、只放开这一组」来算，点哪个都不会落到空结果
  const matchedBy = useCallback(
    (skip: keyof Filters | null) =>
      CODEX_ENTRIES.filter(
        (e) =>
          (skip === "cat" || !filters.cat || e.category === filters.cat) &&
          (skip === "wc" || !filters.wc || e.weaponClass === filters.wc) &&
          (skip === "xp" || filters.xp == null || e.expansion === filters.xp) &&
          (!terms.length || scoreEntry(e, terms, texts?.[e.code]) >= 0),
      ),
    [filters, terms, texts],
  );

  const list = useMemo(() => {
    const hits = matchedBy(null);
    if (terms.length) {
      const score = new Map(hits.map((e) => [e.code, scoreEntry(e, terms, texts?.[e.code])]));
      return hits.sort((a, b) => score.get(b.code)! - score.get(a.code)!);
    }
    if (filters.sort === "name") return hits.sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
    return hits;
  }, [matchedBy, terms, texts, filters.sort]);

  const facets = useMemo(() => {
    const byCat = matchedBy("cat");
    const byWc = matchedBy("wc").filter((e) => e.category === "武器");
    const byXp = matchedBy("xp");
    const count = (arr: CodexEntry[], key: keyof CodexEntry, v: string) =>
      arr.filter((e) => e[key] === v).length;
    return {
      cat: [
        { value: "", label: "全部", n: byCat.length },
        ...CODEX_CATEGORIES.map((c) => ({ value: c, label: c, n: count(byCat, "category", c) })),
      ],
      wc: [
        { value: "", label: "全部", n: byWc.length },
        ...WEAPON_CLASSES.map((c) => ({ value: c, label: c, n: count(byWc, "weaponClass", c) })),
      ],
      xp: [
        { value: null, label: "全部", n: byXp.length },
        ...EXPANSIONS.map((x) => ({
          value: x.key,
          label: x.label,
          n: count(byXp, "expansion", x.key),
        })),
      ],
    };
  }, [matchedBy]);

  const open = useCallback((code: string) => {
    setEntry(code, "push");
    pushed.current = true;
  }, []);

  // 自己压过历史记录就退回去，这样手机返回键和关闭按钮效果一致；从分享链接直接打开的则原地去掉参数
  const close = useCallback(() => {
    if (pushed.current) {
      pushed.current = false;
      window.history.back();
    } else {
      setEntry(null, "replace");
    }
  }, []);

  // 打开的条目不在当前筛选结果里（比如别人发来的链接）时，在全部条目里翻页
  const readerList = openCode && list.some((e) => e.code === openCode) ? list : CODEX_ENTRIES;
  const readerIndex = openCode ? readerList.findIndex((e) => e.code === openCode) : -1;
  const filtered =
    query.trim() !== "" || filters.cat !== "" || filters.wc !== "" || filters.xp != null;

  // 吸顶时在搜索栏右边提示当前筛选，滚到下面也知道自己在看哪一类
  const activeSummary = [
    filters.cat,
    filters.wc,
    filters.xp == null ? "" : EXPANSIONS.find((x) => x.key === filters.xp)?.label,
  ]
    .filter(Boolean)
    .join(" · ");

  const reset = () => {
    setQuery("");
    setFilters({ ...NO_FILTERS, sort: filters.sort });
  };

  return (
    <div className="mt-4">
      <div ref={sentinel} aria-hidden className="h-px" />
      <div
        className={cn(
          "sticky top-12 z-20 -mx-4 flex items-center gap-4 border-b px-4 py-2.5 transition-[background-color,border-color] duration-200 sm:-mx-10 sm:px-10 lg:top-0",
          stuck
            ? "border-white/[0.07] bg-black/80 backdrop-blur-md"
            : "border-transparent bg-transparent",
        )}
      >
        <div className="relative w-full max-w-2xl">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-white/40" />
          <DarkInput
            ref={input}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={wantTexts}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setQuery("");
                e.currentTarget.blur();
              }
            }}
            placeholder="搜索名称、正文、解锁条件或编号"
            aria-label="搜索百科"
            enterKeyHint="search"
            className="h-11 pr-16 pl-9 [&::-webkit-search-cancel-button]:hidden"
          />
          {query ? (
            <button
              type="button"
              aria-label="清空搜索"
              onClick={() => {
                setQuery("");
                input.current?.focus();
              }}
              className="compact-action absolute top-1/2 right-2 flex size-8 -translate-y-1/2 items-center justify-center text-white/50 hover:text-white"
            >
              <X className="size-4" />
            </button>
          ) : (
            <kbd className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 border border-white/15 px-1.5 font-mono text-[11px] text-white/40 [@media(hover:hover)]:block">
              /
            </kbd>
          )}
        </div>
        {stuck ? (
          <span className="hidden shrink-0 text-xs text-white/45 tabular-nums sm:block">
            {activeSummary ? `${activeSummary} · ` : ""}
            {list.length} 条
          </span>
        ) : null}
      </div>

      <div className="mt-4 space-y-2.5">
        <ChipRow label="类别">
          {facets.cat.map((c) => (
            <Chip
              key={c.value}
              label={c.label}
              n={c.n}
              active={filters.cat === c.value}
              onClick={() =>
                setFilters((f) => ({
                  ...f,
                  cat: f.cat === c.value ? "" : c.value,
                  wc: c.value === "武器" ? f.wc : "",
                }))
              }
            />
          ))}
        </ChipRow>
        {filters.cat === "武器" ? (
          <ChipRow label="枪械">
            {facets.wc.map((c) => (
              <Chip
                key={c.value}
                label={c.label}
                n={c.n}
                active={filters.wc === c.value}
                onClick={() => setFilters((f) => ({ ...f, wc: f.wc === c.value ? "" : c.value }))}
              />
            ))}
          </ChipRow>
        ) : null}
        <ChipRow label="资料片">
          {facets.xp.map((c) => (
            <Chip
              key={c.value ?? "all"}
              label={c.label}
              n={c.n}
              active={filters.xp === c.value}
              onClick={() =>
                setFilters((f) => ({
                  ...f,
                  xp: f.xp === c.value || c.value == null ? null : c.value,
                }))
              }
            />
          ))}
        </ChipRow>
      </div>

      <div className="mt-4 flex items-center gap-3 border-t border-white/[0.07] pt-3 text-xs text-white/50">
        <span className="tabular-nums" aria-live="polite">
          {filtered ? (
            <>
              找到 <b className="font-semibold text-white">{list.length}</b> 条
              <span className="text-white/35"> · 共 {CODEX_ENTRIES.length}</span>
            </>
          ) : (
            <>共 {CODEX_ENTRIES.length} 条</>
          )}
        </span>
        {filtered ? (
          <button
            type="button"
            onClick={reset}
            className="inline-action text-amber-400/90 underline-offset-4 hover:underline"
          >
            清空条件
          </button>
        ) : null}
        <span className="flex-1" />
        <Segmented
          label="排序"
          value={terms.length ? "relevance" : filters.sort}
          options={
            terms.length
              ? [{ value: "relevance", label: "按相关度" }]
              : [
                  { value: "game", label: "游戏顺序" },
                  { value: "name", label: "名称" },
                ]
          }
          onChange={(v) => setFilters((f) => ({ ...f, sort: v as Sort }))}
        />
        <Segmented
          label="卡片大小"
          value={density}
          options={(Object.keys(DENSITY) as Density[]).map((d) => ({
            value: d,
            label: DENSITY[d].label,
          }))}
          onChange={(v) => writeDensity(v as Density)}
        />
      </div>

      {list.length ? (
        <div className={cn("mt-5 grid", DENSITY[density].grid)} onPointerEnter={wantTexts}>
          {list.map((e) => (
            <CodexCard
              key={e.code}
              entry={e}
              terms={terms.length ? terms : undefined}
              snippet={terms.length ? bodySnippet(e, terms, texts?.[e.code]) : undefined}
              sizes={DENSITY[density].sizes}
              onOpen={open}
            />
          ))}
        </div>
      ) : (
        <div className="mt-5 border border-dashed border-white/12 px-4 py-14 text-center">
          <div className="text-[15px] font-semibold text-white/85">没有找到相关条目</div>
          <p className="mt-1.5 text-sm text-white/45">
            {terms.length && !texts ? "正文还在加载，稍等片刻；" : ""}
            换个关键词，或者放宽上面的筛选条件
          </p>
          <button
            type="button"
            onClick={reset}
            className="mt-4 h-10 border border-white/20 px-4 text-sm text-white/80 hover:border-white/45 hover:text-white"
          >
            清空条件
          </button>
        </div>
      )}

      {openCode && readerIndex >= 0 ? (
        <CodexReader
          list={readerList}
          index={readerIndex}
          texts={texts}
          terms={terms}
          onIndex={(i) => setEntry(readerList[i].code, "replace")}
          onClose={close}
        />
      ) : null}
    </div>
  );
}

/*
 * 打开的条目只存在地址栏的 ?entry= 里：前进后退、分享链接、页内点击都读同一个来源。
 * history.pushState / replaceState 不会发事件，改完自己广播一次。
 */
const ENTRY_EVENT = "bfm:codex-entry";

function subscribeEntry(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener(ENTRY_EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(ENTRY_EVENT, onChange);
  };
}

function readEntry(): string | null {
  const code = new URLSearchParams(window.location.search).get("entry");
  return code && CODEX_ENTRIES.some((e) => e.code === code) ? code : null;
}

function setEntry(code: string | null, mode: "push" | "replace") {
  const u = new URLSearchParams(window.location.search);
  if (code) u.set("entry", code);
  else u.delete("entry");
  const s = u.toString();
  const url = `${window.location.pathname}${s ? `?${s}` : ""}`;
  if (mode === "push") window.history.pushState(null, "", url);
  else window.history.replaceState(null, "", url);
  window.dispatchEvent(new Event(ENTRY_EVENT));
}

function ChipRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-10 shrink-0 text-xs text-white/40">{label}</span>
      <div className="-mr-4 flex min-w-0 flex-1 [scrollbar-width:none] gap-1.5 overflow-x-auto pr-4 sm:mr-0 sm:flex-wrap sm:pr-0 [&::-webkit-scrollbar]:hidden">
        {children}
      </div>
    </div>
  );
}

function Chip({
  label,
  n,
  active,
  onClick,
}: {
  label: string;
  n: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={!active && n === 0}
      onClick={onClick}
      className={cn(
        "compact-action flex h-9 shrink-0 items-center gap-1.5 border px-3 text-[13px] whitespace-nowrap transition-colors sm:h-8 sm:px-2.5 sm:text-xs",
        active
          ? "border-white bg-white font-semibold text-black"
          : "border-white/20 text-white/65 hover:border-white/45 hover:text-white disabled:cursor-default disabled:border-white/10 disabled:text-white/25",
      )}
    >
      {label}
      <span className={cn("tabular-nums", active ? "text-black/50" : "text-white/35")}>{n}</span>
    </button>
  );
}

function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (v: string) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex border border-white/15">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "compact-action h-8 px-2.5 text-xs transition-colors",
            value === o.value ? "bg-white/12 text-white" : "text-white/50 hover:text-white/85",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
