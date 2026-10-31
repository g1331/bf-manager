"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import Link from "next/link";
import { Quote, RefreshCw } from "lucide-react";
import { usePageState } from "@/hooks/useNavigation";
import { modeLabel } from "@/lib/bf1/catalog";
import {
  getMap,
  MAPS_ORDERED,
  mapImage,
  mapName,
  modeImage,
  type Tip,
  TIPS,
} from "@/lib/bf1/codex/battlefield";
import { searchTerms } from "@/lib/bf1/codex/search";
import { markSeen, pickTip, readSeen } from "@/lib/bf1/codex/tips";
import { Highlight } from "./CodexArticle";
import { Chip, ChipRow, StickySearch } from "./FilterControls";

type Kind = "" | "map" | "mode" | "general";

interface Filters {
  kind: Kind;
  /** 地图或模式代号，"" 不限 */
  tag: string;
}

const NO_FILTERS: Filters = { kind: "", tag: "" };

const kindOf = (t: Tip): Exclude<Kind, ""> =>
  t.type === "map" ? "map" : t.tags.length ? "mode" : "general";

const KINDS: Array<{ key: Exclude<Kind, "">; label: string }> = [
  { key: "map", label: "地图" },
  { key: "mode", label: "模式" },
  { key: "general", label: "通用" },
];

/** 有贴士的地图按资料片顺序排，模式按贴士数从多到少 */
const MAP_TAGS = MAPS_ORDERED.filter((m) => TIPS.some((t) => t.tags.includes(m.id))).map(
  (m) => m.id,
);
const MODE_TAGS = [
  ...new Set(TIPS.filter((t) => kindOf(t) === "mode").flatMap((t) => t.tags)),
].sort(
  (a, b) =>
    TIPS.filter((t) => t.tags.includes(b)).length - TIPS.filter((t) => t.tags.includes(a)).length,
);

function tagLabel(tag: string): string {
  const m = getMap(tag);
  return m ? mapName(m) : modeLabel(tag);
}

function tagHref(tag: string): string {
  return getMap(tag) ? `/bf1/codex/maps/${tag}` : `/bf1/codex/modes/${tag}`;
}

/**
 * 小贴士总表：按地图 / 模式 / 通用筛选，再细到某张图、某个模式；筛选写进地址栏，
 * 地图详情页和 TipLine 的「全部」用 ?tag= 直接跳到对应的筛选。
 */
export function TipsBrowser() {
  const [query, setQuery] = usePageState("tips:q", "");
  const [filters, setFilters] = usePageState<Filters>("tips:filters", NO_FILTERS);
  const ready = useRef(false);
  const deferred = useDeferredValue(query);
  const terms = useMemo(() => searchTerms(deferred), [deferred]);

  useEffect(() => {
    const u = new URLSearchParams(window.location.search);
    if (["q", "kind", "tag"].some((k) => u.has(k))) {
      const tag = u.get("tag") ?? "";
      const kind = u.get("kind");
      const tagKind = MAP_TAGS.includes(tag) ? "map" : MODE_TAGS.includes(tag) ? "mode" : null;
      setQuery(u.get("q") ?? "");
      setFilters(
        tagKind
          ? { kind: tagKind, tag }
          : { kind: KINDS.find((k) => k.key === kind)?.key ?? "", tag: "" },
      );
    }
    ready.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在挂载时读一次
  }, []);

  useEffect(() => {
    if (!ready.current) return;
    const t = setTimeout(() => {
      const u = new URLSearchParams();
      if (query.trim()) u.set("q", query.trim());
      if (filters.tag) u.set("tag", filters.tag);
      else if (filters.kind) u.set("kind", filters.kind);
      const s = u.toString();
      window.history.replaceState(null, "", `${window.location.pathname}${s ? `?${s}` : ""}`);
    }, 250);
    return () => clearTimeout(t);
  }, [query, filters]);

  // 带着 ?tag= 进来时，选中的地图常在横滑行的后半截，把它滚到行中间（只滚这一行，不动页面）
  const tagRow = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const chip = tagRow.current?.querySelector<HTMLElement>('[aria-pressed="true"]');
    const row = chip?.parentElement;
    if (!chip || !row || !filters.tag) return;
    const c = chip.getBoundingClientRect();
    const r = row.getBoundingClientRect();
    row.scrollLeft += c.left - r.left - (r.width - c.width) / 2;
  }, [filters.tag]);

  const searched = terms.length
    ? TIPS.filter((t) => {
        const text = `${t.text} ${t.tags.map(tagLabel).join(" ")}`.toLowerCase();
        return terms.every((w) => text.includes(w));
      })
    : TIPS;
  const byKind = filters.kind ? searched.filter((t) => kindOf(t) === filters.kind) : searched;
  const list = filters.tag ? byKind.filter((t) => t.tags.includes(filters.tag)) : byKind;
  const tagChoices = filters.kind === "map" ? MAP_TAGS : filters.kind === "mode" ? MODE_TAGS : [];
  const filtered = !!query.trim() || !!filters.kind;
  const summary = [
    KINDS.find((k) => k.key === filters.kind)?.label,
    filters.tag ? tagLabel(filters.tag) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const reset = () => {
    setQuery("");
    setFilters(NO_FILTERS);
  };

  return (
    <div className="mt-4">
      <TipShowcase />

      <div className="mt-6">
        <StickySearch
          value={query}
          onChange={setQuery}
          placeholder="搜索贴士内容、地图或模式"
          label="搜索小贴士"
          summary={`${summary ? `${summary} · ` : ""}${list.length} 条`}
        />
      </div>

      <div className="mt-4 space-y-2.5">
        <ChipRow label="分类">
          <Chip label="全部" n={searched.length} active={!filters.kind} onClick={reset} />
          {KINDS.map((k) => (
            <Chip
              key={k.key}
              label={k.label}
              n={searched.filter((t) => kindOf(t) === k.key).length}
              active={filters.kind === k.key}
              onClick={() =>
                setFilters((f) => (f.kind === k.key ? NO_FILTERS : { kind: k.key, tag: "" }))
              }
            />
          ))}
        </ChipRow>
        {tagChoices.length ? (
          <div ref={tagRow}>
            <ChipRow label={filters.kind === "map" ? "地图" : "模式"}>
              <Chip
                label="全部"
                n={byKind.length}
                active={!filters.tag}
                onClick={() => setFilters((f) => ({ ...f, tag: "" }))}
              />
              {tagChoices.map((tag) => (
                <Chip
                  key={tag}
                  label={tagLabel(tag)}
                  n={byKind.filter((t) => t.tags.includes(tag)).length}
                  active={filters.tag === tag}
                  onClick={() => setFilters((f) => ({ ...f, tag: f.tag === tag ? "" : tag }))}
                />
              ))}
            </ChipRow>
          </div>
        ) : null}
      </div>

      <div className="mt-4 flex items-center gap-3 border-t border-white/[0.07] pt-3 text-xs text-white/50">
        <span className="tabular-nums" aria-live="polite">
          {filtered ? (
            <>
              找到 <b className="font-semibold text-white">{list.length}</b> 条
              <span className="text-white/35"> · 共 {TIPS.length}</span>
            </>
          ) : (
            <>共 {TIPS.length} 条</>
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
      </div>

      {list.length ? (
        <ul className="mt-4 grid gap-2 lg:grid-cols-2">
          {list.map((t) => (
            <TipRow key={t.text} tip={t} terms={terms.length ? terms : undefined} />
          ))}
        </ul>
      ) : (
        <div className="mt-5 border border-dashed border-white/12 px-4 py-14 text-center">
          <div className="text-[15px] font-semibold text-white/85">没有找到相关贴士</div>
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

/** 一条贴士：左边是所属地图 / 模式的缩略图，通用贴士放引号 */
function TipRow({ tip, terms }: { tip: Tip; terms?: string[] }) {
  const first = tip.tags[0];
  const thumb = first ? (getMap(first) ? mapImage(first, 480) : modeImage(first, 480)) : null;
  return (
    <li className="flex gap-3 border border-white/[0.07] bg-black/35 p-3 backdrop-blur-sm sm:gap-4">
      <div className="h-[46px] w-[72px] shrink-0 overflow-hidden bg-white/[0.04] ring-1 ring-white/10">
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp
          <img src={thumb} alt="" loading="lazy" className="size-full object-cover" />
        ) : (
          <div className="flex size-full items-center justify-center">
            <Quote className="size-4 text-amber-400/50" aria-hidden />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-relaxed text-white/80">
          <Highlight text={tip.text} terms={terms} />
        </p>
        {tip.tags.length ? (
          <div className="mt-1 flex flex-wrap gap-x-3 text-xs">
            {tip.tags.map((tag) => (
              <Link
                key={tag}
                href={tagHref(tag)}
                prefetch={false}
                className="inline-action text-white/40 hover:text-amber-300"
              >
                {tagLabel(tag)}
              </Link>
            ))}
          </div>
        ) : null}
      </div>
    </li>
  );
}

/**
 * 页首展示的那条贴士放在模块级的小 store 里：服务端快照是空的，客户端第一次读时才随机抽，
 * 这样既不会水合不一致，也不用在 effect 里 setState。离开页面时清掉，下次进来重新抽。
 */
const SHOWCASE_POOL = TIPS.filter((t) => t.type === "map" && t.tags.length);
let showcase: Tip | undefined;
const showcaseListeners = new Set<() => void>();

function drawShowcase(current?: Tip): Tip | undefined {
  const t = pickTip(SHOWCASE_POOL, readSeen(), current?.text);
  if (t) markSeen(t.text);
  return t;
}

function subscribeShowcase(fn: () => void) {
  showcaseListeners.add(fn);
  return () => {
    showcaseListeners.delete(fn);
  };
}

function nextShowcase() {
  showcase = drawShowcase(showcase);
  showcaseListeners.forEach((fn) => fn());
}

/** 页首的「载入画面」：随机一张图配它的一条贴士，可以一直换 */
function TipShowcase() {
  const tip = useSyncExternalStore(
    subscribeShowcase,
    () => (showcase ??= drawShowcase()),
    () => undefined,
  );
  useEffect(
    () => () => {
      showcase = undefined;
    },
    [],
  );

  const map = tip ? getMap(tip.tags[0]) : undefined;
  return (
    // 正文走文档流：长贴士（最长约 150 字）会把卡片撑高，而不是溢出到图片顶上
    <div className="relative flex min-h-64 items-end overflow-hidden border border-white/[0.07] bg-black/50 sm:aspect-[16/6] sm:min-h-0">
      {map ? (
        // eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp
        <img
          key={map.id}
          src={mapImage(map.id)}
          srcSet={`${mapImage(map.id, 480)} 480w, ${mapImage(map.id)} 1000w`}
          sizes="(min-width: 1400px) 1400px, 100vw"
          alt=""
          className="motion-safe:animate-in motion-safe:fade-in absolute inset-0 size-full object-cover duration-700"
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-black/10" />
      <div className="relative flex w-full items-end gap-4 p-4 pt-20 sm:p-6 sm:pt-20 lg:p-8">
        <div
          key={tip?.text}
          className="motion-safe:animate-in motion-safe:fade-in min-w-0 flex-1 duration-500"
        >
          <div className="font-display text-[11px] tracking-[0.2em] text-amber-400/90">
            {map ? (
              <Link
                href={`/bf1/codex/maps/${map.id}`}
                prefetch={false}
                className="inline-action hover:text-amber-300"
              >
                载入中 · {mapName(map)}
              </Link>
            ) : (
              "载入中"
            )}
          </div>
          <p className="mt-2 max-w-3xl text-base leading-relaxed font-medium text-white drop-shadow sm:text-xl sm:leading-relaxed lg:text-2xl lg:leading-relaxed">
            {tip?.text ?? " "}
          </p>
        </div>
        <button
          type="button"
          onClick={nextShowcase}
          aria-label="换一条贴士"
          className="flex h-11 shrink-0 items-center gap-1.5 border border-white/25 bg-black/40 px-3 text-sm text-white/85 backdrop-blur-sm transition-colors hover:border-amber-400/60 hover:text-amber-200 sm:h-10"
        >
          <RefreshCw className="size-4" />
          <span className="hidden sm:inline">换一条</span>
        </button>
      </div>
    </div>
  );
}
