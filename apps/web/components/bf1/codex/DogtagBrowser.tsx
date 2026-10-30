"use client";

import { useDeferredValue, useEffect, useMemo, useRef } from "react";
import { usePageState } from "@/hooks/useNavigation";
import { EXPANSIONS } from "@/lib/bf1/codex/codex";
import { type Dogtag, DOGTAG_CATEGORIES, DOGTAGS } from "@/lib/bf1/codex/collection";
import { searchTerms } from "@/lib/bf1/codex/search";
import { cn } from "@/lib/utils";
import { DogtagCard } from "./DogtagCard";
import { Chip, ChipRow, Segmented, StickySearch } from "./FilterControls";

interface Filters {
  cat: string;
  /** "" 不限 */
  side: "" | Dogtag["side"];
  /** null 不限；"" 是本体 */
  xp: string | null;
}

const NO_FILTERS: Filters = { cat: "", side: "", xp: null };

function matches(t: Dogtag, terms: string[]) {
  const text = `${t.id} ${t.name} ${t.category} ${t.description}`.toLowerCase();
  return terms.every((w) => text.includes(w));
}

/**
 * 狗牌列表：搜名称和描述，按分类、基本 / 高级、资料片筛选；筛选写进地址栏。
 * 点开进独立详情页（那里是 3D 检视器，太重，不做成列表上的弹层）。
 */
export function DogtagBrowser() {
  const [query, setQuery] = usePageState("dogtags:q", "");
  const [filters, setFilters] = usePageState<Filters>("dogtags:filters", NO_FILTERS);
  const ready = useRef(false);
  const deferred = useDeferredValue(query);
  const terms = useMemo(() => searchTerms(deferred), [deferred]);

  useEffect(() => {
    const u = new URLSearchParams(window.location.search);
    if (["q", "cat", "side", "xp"].some((k) => u.has(k))) {
      const side = u.get("side");
      const xp = u.get("xp");
      setQuery(u.get("q") ?? "");
      setFilters({
        cat: u.get("cat") ?? "",
        side: side === "front" || side === "back" ? side : "",
        xp: xp == null ? null : xp === "base" ? "" : xp,
      });
    }
    ready.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在挂载时读一次
  }, []);

  useEffect(() => {
    if (!ready.current) return;
    const t = setTimeout(() => {
      const u = new URLSearchParams();
      if (query.trim()) u.set("q", query.trim());
      if (filters.cat) u.set("cat", filters.cat);
      if (filters.side) u.set("side", filters.side);
      if (filters.xp != null) u.set("xp", filters.xp || "base");
      const s = u.toString();
      window.history.replaceState(null, "", `${window.location.pathname}${s ? `?${s}` : ""}`);
    }, 250);
    return () => clearTimeout(t);
  }, [query, filters]);

  const matchedBy = (skip: keyof Filters | null) =>
    DOGTAGS.filter(
      (t) =>
        (skip === "cat" || !filters.cat || t.category === filters.cat) &&
        (skip === "side" || !filters.side || t.side === filters.side) &&
        (skip === "xp" || filters.xp == null || t.expansion === filters.xp) &&
        (!terms.length || matches(t, terms)),
    );
  const list = matchedBy(null);
  const byCat = matchedBy("cat");
  const byXp = matchedBy("xp");
  const filtered = !!query.trim() || !!filters.cat || !!filters.side || filters.xp != null;
  const summary = [
    filters.cat,
    filters.side === "front" ? "基本" : filters.side === "back" ? "高级" : "",
    filters.xp == null ? "" : EXPANSIONS.find((x) => x.key === filters.xp)?.label,
  ]
    .filter(Boolean)
    .join(" · ");
  const reset = () => {
    setQuery("");
    setFilters(NO_FILTERS);
  };

  return (
    <div className="mt-4">
      <StickySearch
        value={query}
        onChange={setQuery}
        placeholder="搜索狗牌名称或描述"
        label="搜索狗牌"
        summary={`${summary ? `${summary} · ` : ""}${list.length} 枚`}
      />

      <div className="mt-4 space-y-2.5">
        <ChipRow label="分类">
          <Chip
            label="全部"
            n={byCat.length}
            active={!filters.cat}
            onClick={() => setFilters((f) => ({ ...f, cat: "" }))}
          />
          {DOGTAG_CATEGORIES.map((c) => (
            <Chip
              key={c}
              label={c}
              n={byCat.filter((t) => t.category === c).length}
              active={filters.cat === c}
              onClick={() => setFilters((f) => ({ ...f, cat: f.cat === c ? "" : c }))}
            />
          ))}
        </ChipRow>
        <ChipRow label="资料片">
          <Chip
            label="全部"
            n={byXp.length}
            active={filters.xp == null}
            onClick={() => setFilters((f) => ({ ...f, xp: null }))}
          />
          {EXPANSIONS.map((x) => (
            <Chip
              key={x.key}
              label={x.label}
              n={byXp.filter((t) => t.expansion === x.key).length}
              active={filters.xp === x.key}
              onClick={() => setFilters((f) => ({ ...f, xp: f.xp === x.key ? null : x.key }))}
            />
          ))}
        </ChipRow>
      </div>

      <div className="mt-4 flex items-center gap-3 border-t border-white/[0.07] pt-3 text-xs text-white/50">
        <span className="tabular-nums" aria-live="polite">
          {filtered ? (
            <>
              找到 <b className="font-semibold text-white">{list.length}</b> 枚
              <span className="text-white/35"> · 共 {DOGTAGS.length}</span>
            </>
          ) : (
            <>共 {DOGTAGS.length} 枚</>
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
          label="狗牌种类"
          value={filters.side}
          options={[
            { value: "", label: "全部" },
            { value: "front", label: "基本" },
            { value: "back", label: "高级" },
          ]}
          onChange={(v) => setFilters((f) => ({ ...f, side: v as Filters["side"] }))}
        />
      </div>

      {list.length ? (
        <div
          className={cn(
            "mt-5 grid grid-cols-3 gap-x-2 gap-y-5 sm:grid-cols-[repeat(auto-fill,minmax(132px,1fr))] sm:gap-x-4 sm:gap-y-7",
          )}
        >
          {list.map((t) => (
            <DogtagCard key={t.id} tag={t} terms={terms.length ? terms : undefined} />
          ))}
        </div>
      ) : (
        <div className="mt-5 border border-dashed border-white/12 px-4 py-14 text-center">
          <div className="text-[15px] font-semibold text-white/85">没有找到相关狗牌</div>
          <p className="mt-1.5 text-sm text-white/45">换个关键词，或者放宽上面的筛选条件</p>
          <button
            type="button"
            onClick={reset}
            className="mt-4 h-10 border border-white/20 px-4 text-sm text-white/80 hover:border-white/45 hover:text-white"
          >
            清空条件
          </button>
        </div>
      )}
    </div>
  );
}
