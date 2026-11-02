"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { usePageState } from "@/hooks/useNavigation";
import { useParams, useRouter } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  Lock,
  MapPin,
  RotateCw,
  Search,
  SlidersHorizontal,
  Users,
  X,
} from "lucide-react";
import { DarkInput } from "@/components/common/DarkInput";
import { CountryFlag } from "@/components/common/CountryFlag";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { cn } from "@/lib/utils";
import { ServerListSkeleton } from "@/components/layout/PageSkeleton";
import { ServerSubTabs } from "@/components/bf1/ServerSubTabs";
import { pingSiteLabel, pingSiteCountry } from "@/lib/bf1/pingsite";
import {
  BF1_MAPS,
  BF1_MODES,
  BF1_REGIONS,
  mapLabel,
  modeLabel,
  regionLabel,
} from "@/lib/bf1/catalog";
import type {
  ServerFacets,
  ServerFilterOptions,
  ServerFilterRule,
  ServerSummary,
} from "@/lib/api/bf1";
import { bf1Queries, type ServerListSelection } from "@/lib/queries/bf1";
import {
  DEFAULT_FILTERS,
  EMPTY_SLOT_OPTIONS,
  SIZE_OPTIONS,
  filtersFromSearch,
  filtersToSearch,
  loadStoredFilters,
  presetActive,
  pruneRules,
  rulesToParams,
  setRule,
  storeFilters,
  togglePreset,
  type FilterState,
  type RuleValue,
} from "@/lib/bf1/server-filters";
import { TipLine } from "@/components/bf1/codex/TipLine";

const PAGE_SIZE = 50;

/** 防抖取值：value 停止变化 delayMs 后才返回新值，用于把高频筛选改动合并为一次请求 */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

function toggle<T>(arr: T[], val: T): T[] {
  return arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val];
}

const noopSubscribe = () => () => {};

/**
 * 筛选条件先从 URL（分享链接、返回上一页）或 localStorage（上次的选择）读出来再渲染列表，
 * 免得先按默认条件请求一次。服务端渲染与水合时还读不到，渲染空白；客户端跳转进来时首帧就能读到。
 */
export default function ServerListPage() {
  const params = useParams<{ game: string }>();
  const onClient = useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
  const initial = useMemo(
    () =>
      onClient
        ? (filtersFromSearch(window.location.search) ?? loadStoredFilters() ?? DEFAULT_FILTERS)
        : null,
    [onClient],
  );
  if (!initial) return null;
  return <ServerBrowser game={params.game} initial={initial} />;
}

/** 条件摘要里的一项，带撤销动作 */
interface SummaryChip {
  id: string;
  label: string;
  remove: () => void;
}

function ServerBrowser({ game, initial }: { game: string; initial: FilterState }) {
  const router = useRouter();
  // 进详情再返回时保留已展开的条数
  const [visibleCount, setVisibleCount] = usePageState(`${game}-servers-count`, PAGE_SIZE);
  const [rawFilters, setFilters] = useState<FilterState>(initial);
  const filterOptions = useQuery(bf1Queries.serverFilterOptions());
  // URL 或 localStorage 里可能带着已下线、手改出来的规则，按目录裁掉再用；裁掉的随下次写回一并清除
  const filters = useMemo(
    () =>
      filterOptions.data
        ? { ...rawFilters, rules: pruneRules(rawFilters.rules, filterOptions.data) }
        : rawFilters,
    [rawFilters, filterOptions.data],
  );
  // 带规则时等目录到了再查，免得把不认识的规则发给后端换来整单失败；目录拉不到就照原样发
  const catalogReady =
    Object.keys(rawFilters.rules).length === 0 || !!filterOptions.data || filterOptions.isError;

  // 筛选写回 URL 与 localStorage。名称与「含空服」只放 URL：前者容易忘了清，后者每次都要请求 EA
  useEffect(() => {
    storeFilters({ ...filters, nameFilter: "", includeEmpty: false });
    const qs = filtersToSearch(filters);
    const url = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
    if (url !== `${window.location.pathname}${window.location.search}`) {
      window.history.replaceState(null, "", url);
    }
  }, [filters]);

  // 全部条件交后端筛选（默认在全服快照上筛并给出各选项计数，按名称搜或含空服时走 EA 检索），
  // 而非仅在已加载的前若干条结果内过滤，避免冷门条件被结果上限截断。
  // 勾选合并 300ms 防抖，避免连续勾选产生多次请求；排序保证勾选顺序不同不产生多份缓存。
  const selection = useMemo<ServerListSelection>(
    () => ({
      maps: [...filters.maps].sort(),
      modes: [...filters.modes].sort(),
      regions: [...filters.regions].sort(),
      sizes: [...filters.sizes].sort((a, b) => a - b),
      serverTypes: [...filters.serverTypes].sort(),
      rules: rulesToParams(filters.rules),
      slots: [...filters.emptySlots].sort(),
      includeEmpty: filters.includeEmpty,
    }),
    [
      filters.maps,
      filters.modes,
      filters.regions,
      filters.sizes,
      filters.serverTypes,
      filters.rules,
      filters.emptySlots,
      filters.includeEmpty,
    ],
  );
  const debouncedSelection = useDebouncedValue(selection, 300);
  // 名称同样下推到 EA（包含匹配、大小写不敏感）以补全前若干条之外的同名服务器，打字停止
  // 450ms 后才请求；同时下方 filtered 用即时 nameFilter 对当前结果二次过滤，保证打字即时反馈。
  const debouncedName = useDebouncedValue(filters.nameFilter.trim(), 450);

  const servers = useQuery({
    ...bf1Queries.servers(debouncedSelection, debouncedName),
    // 防抖值追上裁剪后的规则才发请求
    enabled: catalogReady && debouncedSelection.rules.join() === selection.rules.join(),
    // 刷新 / 切换筛选期间保留上一次结果，避免请求期间 servers.data 变 undefined 导致列表与筛选面板闪断。
    placeholderData: keepPreviousData,
  });

  // servers.data 为 undefined 时回落空数组；包进 useMemo 保持引用稳定，
  // 避免每次 render 生成新数组导致下游 filtered useMemo 失效（exhaustive-deps）。
  const allItems = useMemo(() => servers.data?.items ?? [], [servers.data?.items]);
  const facets = servers.data?.facets ?? null;

  // 名称做即时包含过滤以提供打字反馈，其余条件都已在服务端生效
  const sorted = useMemo(() => {
    const nameNeedle = filters.nameFilter.trim().toLowerCase();
    const items = nameNeedle
      ? allItems.filter((s) => s.name.toLowerCase().includes(nameNeedle))
      : allItems;
    return [...items].sort((a, b) => b.player_count - a.player_count);
  }, [allItems, filters.nameFilter]);

  const visibleItems = sorted.slice(0, visibleCount);
  const hasMore = visibleCount < sorted.length;

  const [filterSheetOpen, setFilterSheetOpen] = useState(false);

  const resetFilters = () => {
    setFilters(DEFAULT_FILTERS);
    setVisibleCount(PAGE_SIZE);
  };
  const patch = (p: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...p }));
    setVisibleCount(PAGE_SIZE);
  };

  const summaryChips = buildSummaryChips(filters, patch, filterOptions.data);
  const filtersActive = summaryChips.length > 0;
  // 手机端「筛选」按钮上的角标：名称以外生效的条件数（名称有单独的搜索框）
  const optionCount = summaryChips.filter((c) => c.id !== "name").length;

  const ui: FilterUI = { filters, patch, options: filterOptions.data, facets };

  return (
    <main className="flex flex-col gap-4 py-6 text-white lg:h-full lg:min-h-0">
      {/* 标题行 + 右侧筛选摘要、刷新 */}
      <header className="flex flex-wrap items-end justify-between gap-3 lg:shrink-0">
        <div>
          <div className="font-display flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
            <span className="h-[2px] w-6 bg-amber-500" />
            Servers
          </div>
          <h1 className="mt-1.5 text-2xl font-bold tracking-wide sm:text-3xl">服务器浏览器</h1>
        </div>
        <div className="flex items-center gap-3 text-sm text-white/55">
          <span className="hidden items-center gap-1.5 sm:inline-flex">
            <span className="text-white/40">筛选条件：</span>
            <span className="max-w-[28rem] truncate text-white/75">
              {summaryChips.length ? summaryChips.map((c) => c.label).join("、") : "无"}
            </span>
          </span>
          <button
            type="button"
            onClick={() => servers.refetch()}
            disabled={servers.isFetching}
            className="inline-flex items-center gap-1.5 text-white/55 transition-colors hover:text-white disabled:opacity-50"
          >
            <RotateCw className={cn("size-4", servers.isFetching && "animate-spin")} />
            刷新
          </button>
        </div>
      </header>

      {/* 子标签：游戏（本页）/ 您的服务器（可点）；我的最爱 / 最近游玩 暂未接入置灰 */}
      <ServerSubTabs game={game} active="browse" />

      {/* 手机端工具栏：搜索框 + 筛选按钮（筛选面板改成底部抽屉，不再排在整张列表后面） */}
      <div className="flex gap-2 lg:hidden">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-white/40" />
          <DarkInput
            value={filters.nameFilter}
            onChange={(e) => patch({ nameFilter: e.target.value })}
            placeholder="搜索服务器名称"
            className="h-11 pl-9"
          />
        </div>
        <button
          type="button"
          onClick={() => setFilterSheetOpen(true)}
          className={cn(
            "flex h-11 shrink-0 items-center gap-1.5 rounded-md border px-3.5 text-sm font-medium transition-colors",
            optionCount > 0
              ? "border-amber-400/60 text-amber-300"
              : "border-white/15 text-white/80 active:bg-white/5",
          )}
        >
          <SlidersHorizontal className="size-4" />
          筛选
          {optionCount > 0 ? <span className="tabular-nums">{optionCount}</span> : null}
        </button>
      </div>
      <Drawer open={filterSheetOpen} onOpenChange={setFilterSheetOpen}>
        <DrawerContent className="dark max-h-[85dvh] border-white/10 bg-zinc-950 text-white">
          <DrawerHeader className="pb-2 text-left">
            <DrawerTitle className="text-base">筛选服务器</DrawerTitle>
          </DrawerHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-4">
            <FilterSheetBody ui={ui} summaryChips={summaryChips} />
          </div>
          <DrawerFooter className="flex-row border-t border-white/10">
            <Button
              variant="outline"
              className="flex-1 border-white/15 bg-transparent text-white"
              disabled={!filtersActive}
              onClick={resetFilters}
            >
              重设
            </Button>
            <Button className="flex-1" onClick={() => setFilterSheetOpen(false)}>
              查看 {sorted.length} 个服务器
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* 主体：左密集表格 + 右筛选面板。桌面端整块填满剩余高度，仅列表内部滚动 */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="@container/list flex min-w-0 flex-col lg:min-h-0">
          {servers.isLoading ? (
            <ServerListSkeleton />
          ) : sorted.length > 0 ? (
            <>
              {/* 表头常驻，不随列表滚动 */}
              <div className="hidden items-center gap-4 border-b border-white/10 px-3 pb-2 text-[11px] font-semibold tracking-[0.16em] text-white/40 uppercase lg:shrink-0 @[28rem]/list:flex">
                <span className="flex-1">名称</span>
                <span className="w-28 text-right">玩家</span>
                <span className="hidden w-24 text-right @[36rem]/list:block">节点</span>
              </div>
              {/* 列表滚动区：桌面端唯一的内部滚动容器 */}
              <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
                <ul>
                  {visibleItems.map((s, i) => (
                    // 搜索结果里 server_id 多为 0（RSP serverId 仅详情接口返回），用 game_id
                    // 作为唯一键，空值回退到索引，避免重复 key。
                    <ServerRow
                      key={s.game_id ?? `idx-${i}`}
                      server={s}
                      onClick={() => s.game_id && router.push(`/${game}/server/${s.game_id}`)}
                    />
                  ))}
                </ul>
                <div className="flex flex-col items-center gap-2 pt-4 text-sm text-white/45">
                  <span className="tabular-nums">
                    已显示 {visibleItems.length} / {sorted.length} 条
                  </span>
                  {hasMore ? (
                    <Button
                      variant="outline"
                      onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                      className="border-white/15 px-8 text-white hover:bg-white/5"
                    >
                      加载更多
                    </Button>
                  ) : null}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="rounded-sm border border-dashed border-white/15 py-16 text-center text-sm text-white/45">
                {filtersActive ? "当前筛选条件下没有匹配的服务器" : "未找到匹配的服务器"}
              </div>
              <TipLine className="mt-3" />
            </>
          )}
        </section>

        {/* 筛选面板常驻，复刻游戏右侧固定筛选栏；自身满高，条目过多时仅面板内部滚动。
            手机端改由工具栏的「筛选」按钮打开底部抽屉 */}
        <FilterPanel
          ui={ui}
          reset={resetFilters}
          filtersActive={filtersActive}
          summaryChips={summaryChips}
        />
      </div>
    </main>
  );
}

/** 当前生效的条件，逐项可撤销。快捷标签的规则全部生效时合成一项，不把几十个开关逐个列出 */
function buildSummaryChips(
  f: FilterState,
  patch: (p: Partial<FilterState>) => void,
  options: ServerFilterOptions | undefined,
): SummaryChip[] {
  const chips: SummaryChip[] = [];
  const typeLabel = (id: string) => options?.server_types.find((t) => t.id === id)?.label ?? id;
  f.serverTypes.forEach((id) =>
    chips.push({
      id: `type:${id}`,
      label: typeLabel(id),
      remove: () => patch({ serverTypes: f.serverTypes.filter((x) => x !== id) }),
    }),
  );
  const covered = new Set<string>();
  options?.presets.forEach((p) => {
    if (!presetActive(f.rules, p.rules) || Object.keys(p.rules).some((k) => covered.has(k))) return;
    Object.keys(p.rules).forEach((k) => covered.add(k));
    chips.push({
      id: `preset:${p.id}`,
      label: p.label,
      remove: () => patch({ rules: togglePreset(f.rules, p.rules) }),
    });
  });
  const ruleByKey = new Map(options?.groups.flatMap((g) => g.rules.map((r) => [r.key, r])) ?? []);
  Object.entries(f.rules).forEach(([key, value]) => {
    if (covered.has(key)) return;
    const rule = ruleByKey.get(key);
    const valueLabel = rule?.options.find((o) => o.value === value)?.label ?? value;
    chips.push({
      id: `rule:${key}`,
      label: `${rule?.label ?? key}：${valueLabel}`,
      remove: () => patch({ rules: setRule(f.rules, key, null) }),
    });
  });
  const list = <K extends "modes" | "maps" | "regions" | "emptySlots">(
    key: K,
    label: (v: string) => string,
  ) =>
    (f[key] as string[]).forEach((v) =>
      chips.push({
        id: `${key}:${v}`,
        label: label(v),
        remove: () => patch({ [key]: (f[key] as string[]).filter((x) => x !== v) }),
      }),
    );
  list("modes", modeLabel);
  list("maps", mapLabel);
  list("regions", regionLabel);
  list("emptySlots", (id) => `空位 ${EMPTY_SLOT_OPTIONS.find((o) => o.id === id)?.label ?? id}`);
  f.sizes.forEach((n) =>
    chips.push({
      id: `size:${n}`,
      label: `${n} 人`,
      remove: () => patch({ sizes: f.sizes.filter((x) => x !== n) }),
    }),
  );
  if (f.includeEmpty)
    chips.push({ id: "empty", label: "含空服", remove: () => patch({ includeEmpty: false }) });
  if (f.nameFilter.trim())
    chips.push({
      id: "name",
      label: `名称含「${f.nameFilter.trim()}」`,
      remove: () => patch({ nameFilter: "" }),
    });
  return chips;
}

/* ----------------------------- 服务器表行 ----------------------------- */

function ServerRow({ server, onClick }: { server: ServerSummary; onClick: () => void }) {
  const mapLabel = server.map_display_name ?? server.map_name;
  const modeLabel = server.mode_display_name ?? server.game_mode;
  const flagCode = server.country ?? pingSiteCountry(server.ping_site);
  const node = pingSiteLabel(server.ping_site) ?? server.region_display_name ?? server.region;
  const fill =
    server.max_player_count > 0
      ? Math.round((server.player_count / server.max_player_count) * 100)
      : 0;
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="group flex w-full items-center gap-3 border-b border-white/[0.06] px-2 py-2.5 text-left transition-colors hover:bg-white/[0.06] @[28rem]/list:gap-4 @[28rem]/list:px-3"
      >
        {/* 地图缩略图：列表窄时（手机、1024 宽旁边还有筛选栏）缩小，把宽度让给服务器名 */}
        <div className="relative h-11 w-16 shrink-0 overflow-hidden rounded-sm bg-white/[0.04] @[36rem]/list:h-14 @[36rem]/list:w-24">
          {server.map_image_url ? (
            // EA CDN 自带缩放与缓存，不走 next/image
            <img
              src={server.map_image_url}
              alt={mapLabel ?? ""}
              loading="lazy"
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <MapPin className="size-4 text-white/20" />
            </div>
          )}
        </div>

        {/* 名称 + 副信息 */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-sm font-medium text-white" title={server.name}>
              {server.name}
            </span>
            {server.has_password ? <Lock className="size-3.5 shrink-0 text-white/40" /> : null}
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-white/45">
            <CountryFlag code={flagCode} className="leading-none" />
            {modeLabel ? <span className="shrink-0 whitespace-nowrap">{modeLabel}</span> : null}
            {mapLabel ? (
              <>
                <span className="text-white/25">·</span>
                <span className="truncate">{mapLabel}</span>
              </>
            ) : null}
            {server.tick_rate ? (
              <>
                <span className="text-white/25">·</span>
                <span className="shrink-0 tabular-nums">{server.tick_rate} HZ</span>
              </>
            ) : null}
          </div>
        </div>

        {/* 玩家数：满员叠加排队人数（如 64 / 64 [1]）时内容偏长，固定列宽并禁止折行 */}
        <div className="flex shrink-0 items-center justify-end gap-1.5 text-sm whitespace-nowrap tabular-nums @[28rem]/list:w-28">
          <Users className="hidden size-3.5 text-white/35 @[28rem]/list:block" />
          <span className={cn(fill >= 100 ? "text-amber-300" : "text-white")}>
            {server.player_count}
          </span>
          <span className="text-white/40">/ {server.max_player_count}</span>
          {server.queue_count > 0 ? (
            <span className="text-white/45">[{server.queue_count}]</span>
          ) : null}
        </div>

        {/* 节点（数据中心）：EA 不返回 ping 数值，展示节点城市，对应游戏内 ping 所测目标 */}
        <div className="hidden w-24 shrink-0 justify-end text-right text-xs text-white/55 @[36rem]/list:flex">
          <span className="truncate" title={server.ping_site ?? undefined}>
            {node ?? "—"}
          </span>
        </div>
      </button>
    </li>
  );
}

/* ----------------------------- 筛选面板共用 ----------------------------- */

interface FilterUI {
  filters: FilterState;
  patch: (p: Partial<FilterState>) => void;
  options: ServerFilterOptions | undefined;
  /** 走 EA 搜索时没有计数，为 null */
  facets: ServerFacets | null;
}

/** 选项旁的结果数；没有计数时不显示 */
function CountBadge({ count }: { count: number | undefined }) {
  if (count === undefined) return null;
  return <span className="ml-auto pl-2 text-xs text-white/35 tabular-nums">{count}</span>;
}

/** 已选条件：每项可单独撤销 */
function SummaryChipList({ chips }: { chips: SummaryChip[] }) {
  if (!chips.length) return <p className="text-xs text-white/35">未设置筛选条件</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <button
          key={c.id}
          type="button"
          onClick={c.remove}
          aria-label={`移除 ${c.label}`}
          className="compact-action inline-flex h-7 items-center gap-1 rounded-sm bg-white/8 pr-1.5 pl-2 text-xs text-white/75 transition-colors hover:bg-white/15 hover:text-white"
        >
          {c.label}
          <X className="size-3 text-white/45" />
        </button>
      ))}
    </div>
  );
}

/** 快捷标签：一次叠加一组开关，可多选 */
function PresetChips({ ui, large }: { ui: FilterUI; large?: boolean }) {
  const { filters, patch, options, facets } = ui;
  if (!options) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {options.presets.map((p) => (
        <Chip
          key={p.id}
          large={large}
          selected={presetActive(filters.rules, p.rules)}
          count={facets?.presets[p.id]}
          onClick={() => patch({ rules: togglePreset(filters.rules, p.rules) })}
        >
          {p.label}
        </Chip>
      ))}
    </div>
  );
}

/** 更多玩法设置：载具 / 兵种 / 武器 / 进阶四组开关和「规则」组的倍率，默认都是「不限」 */
function RuleGroups({ ui, large }: { ui: FilterUI; large?: boolean }) {
  const { filters, patch, options, facets } = ui;
  if (!options) return null;
  return (
    <>
      {options.groups.map((g) => (
        <FilterSection
          key={g.id}
          title={g.label}
          count={g.rules.filter((r) => filters.rules[r.key]).length}
          scroll={!large}
        >
          <ul className="space-y-1.5">
            {g.rules.map((r) => (
              <RuleRow
                key={r.key}
                rule={r}
                large={large}
                value={filters.rules[r.key] ?? null}
                counts={facets?.rules[r.key]}
                onChange={(v) => patch({ rules: setRule(filters.rules, r.key, v) })}
              />
            ))}
          </ul>
        </FilterSection>
      ))}
    </>
  );
}

/**
 * 一条规则的单选：「不限」加上各取值，取值旁边是选上后的结果数。开关只有开 / 关两档，和名称排一行；
 * 倍率最多五档，名称单独一行、档位平分整行。
 */
function RuleRow({
  rule,
  value,
  counts,
  onChange,
  large,
}: {
  rule: ServerFilterRule;
  value: RuleValue | null;
  counts: Record<string, number> | undefined;
  onChange: (v: RuleValue | null) => void;
  large?: boolean;
}) {
  const stacked = rule.options.length > 2;
  const segs: { v: RuleValue | null; label: string; count?: number }[] = [
    { v: null, label: "不限" },
    ...rule.options.map((o) => ({ v: o.value, label: o.label, count: counts?.[o.value] })),
  ];
  return (
    <li className={cn("flex gap-x-2 gap-y-1.5", stacked ? "flex-col" : "items-center")}>
      <span className="min-w-0 flex-1 truncate text-sm text-white/75" title={rule.label}>
        {rule.label}
      </span>
      <div className="flex shrink-0 overflow-hidden rounded-sm border border-white/12">
        {segs.map((seg) => {
          const selected = value === seg.v;
          const empty = seg.count === 0 && !selected;
          return (
            <button
              key={seg.label}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(seg.v)}
              className={cn(
                "compact-action flex items-center justify-center gap-x-1 border-l border-white/12 text-xs transition-colors first:border-l-0",
                // 固定宽度或平分整行，计数位数不同时各行也能对齐
                stacked ? "min-w-0 flex-1 flex-wrap" : large ? "w-16" : "w-12",
                large ? "h-11" : stacked ? "h-9" : "h-7",
                selected
                  ? seg.v === null
                    ? "bg-white/10 text-white"
                    : "bg-amber-400/20 text-amber-200"
                  : empty
                    ? "text-white/25 hover:bg-white/5"
                    : "text-white/70 hover:bg-white/8 hover:text-white",
              )}
            >
              {seg.label}
              {seg.count !== undefined ? (
                <span
                  className={cn(
                    "tabular-nums",
                    stacked && "w-full text-center text-[10px] leading-none",
                    selected ? "text-amber-200/70" : "text-white/35",
                  )}
                >
                  {seg.count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </li>
  );
}

/* ----------------------------- 右侧筛选面板 ----------------------------- */

function FilterPanel({
  ui,
  reset,
  filtersActive,
  summaryChips,
}: {
  ui: FilterUI;
  reset: () => void;
  filtersActive: boolean;
  summaryChips: SummaryChip[];
}) {
  const { filters, patch, options, facets } = ui;
  return (
    <aside className="hidden space-y-5 lg:block lg:min-h-0 lg:self-stretch lg:overflow-y-auto lg:pr-1">
      {/* 您的筛选条件：当前生效条件的标签集，点一下撤销 */}
      <section>
        <PanelTitle>您的筛选条件</PanelTitle>
        <div className="mt-3">
          <SummaryChipList chips={summaryChips} />
        </div>
      </section>

      {options ? (
        <section>
          <PanelTitle>服务器类型</PanelTitle>
          <div className="mt-1">
            {options.server_types.map((t) => (
              <GameCheckbox
                key={t.id}
                checked={filters.serverTypes.includes(t.id)}
                onChange={() => patch({ serverTypes: toggle(filters.serverTypes, t.id) })}
                label={t.label}
                count={facets?.server_types[t.id]}
              />
            ))}
          </div>
        </section>
      ) : null}

      {options ? (
        <section>
          <PanelTitle>玩法</PanelTitle>
          <div className="mt-3">
            <PresetChips ui={ui} />
          </div>
        </section>
      ) : null}

      {/* 快速筛选：可折叠多选分区 */}
      <section>
        <PanelTitle>快速筛选</PanelTitle>
        <div className="mt-1">
          <FilterSection title="游戏模式" count={filters.modes.length} defaultOpen>
            {BF1_MODES.map((m) => (
              <GameCheckbox
                key={m.code}
                checked={filters.modes.includes(m.code)}
                onChange={() => patch({ modes: toggle(filters.modes, m.code) })}
                label={m.label}
              />
            ))}
          </FilterSection>

          <FilterSection title="地图" count={filters.maps.length}>
            {BF1_MAPS.map((m) => (
              <GameCheckbox
                key={m.code}
                checked={filters.maps.includes(m.code)}
                onChange={() => patch({ maps: toggle(filters.maps, m.code) })}
                label={m.label}
              />
            ))}
          </FilterSection>

          <FilterSection title="区域" count={filters.regions.length}>
            {BF1_REGIONS.map((r) => (
              <GameCheckbox
                key={r.code}
                checked={filters.regions.includes(r.code)}
                onChange={() => patch({ regions: toggle(filters.regions, r.code) })}
                label={r.label}
              />
            ))}
          </FilterSection>

          <FilterSection title="空位" count={filters.emptySlots.length}>
            {EMPTY_SLOT_OPTIONS.map((o) => (
              <GameCheckbox
                key={o.id}
                checked={filters.emptySlots.includes(o.id)}
                onChange={() => patch({ emptySlots: toggle(filters.emptySlots, o.id) })}
                label={o.label}
              />
            ))}
          </FilterSection>

          <FilterSection title="服务器规模" count={filters.sizes.length}>
            {SIZE_OPTIONS.map((n) => (
              <GameCheckbox
                key={n}
                checked={filters.sizes.includes(n)}
                onChange={() => patch({ sizes: toggle(filters.sizes, n) })}
                label={String(n)}
              />
            ))}
          </FilterSection>

          <FilterSection title="空服" count={filters.includeEmpty ? 1 : 0}>
            <GameCheckbox
              checked={filters.includeEmpty}
              onChange={() => patch({ includeEmpty: !filters.includeEmpty })}
              label="包含 0 人服务器（EA 抽样，结果不全）"
            />
          </FilterSection>
        </div>
      </section>

      {options ? (
        <section>
          <PanelTitle>更多玩法设置</PanelTitle>
          <div className="mt-1">
            <RuleGroups ui={ui} />
          </div>
        </section>
      ) : null}

      {/* 以名称筛选：结果内二次过滤 */}
      <DarkInput
        value={filters.nameFilter}
        onChange={(e) => patch({ nameFilter: e.target.value })}
        placeholder="以名称筛选…"
      />

      <button
        type="button"
        onClick={reset}
        disabled={!filtersActive}
        className="w-full rounded-sm border border-white/15 py-2.5 text-sm font-medium tracking-wide text-white/80 transition-colors hover:bg-white/5 disabled:opacity-40"
      >
        重设筛选条件
      </button>
    </aside>
  );
}

/* ----------------------------- 手机端筛选抽屉 ----------------------------- */

/** 手机端底部抽屉里的筛选：常用分组平铺成标签块，开关类收进可折叠分组，只有抽屉本身一层滚动 */
function FilterSheetBody({ ui, summaryChips }: { ui: FilterUI; summaryChips: SummaryChip[] }) {
  const { filters, patch, options, facets } = ui;
  return (
    <div className="space-y-5 pb-4">
      {summaryChips.length ? <SummaryChipList chips={summaryChips} /> : null}
      {options ? (
        <ChipGroup title="服务器类型">
          {options.server_types.map((t) => (
            <Chip
              key={t.id}
              large
              selected={filters.serverTypes.includes(t.id)}
              count={facets?.server_types[t.id]}
              onClick={() => patch({ serverTypes: toggle(filters.serverTypes, t.id) })}
            >
              {t.label}
            </Chip>
          ))}
        </ChipGroup>
      ) : null}
      {options ? (
        <section>
          <h3 className="mb-2.5 text-[13px] font-medium text-white/55">玩法</h3>
          <PresetChips ui={ui} large />
        </section>
      ) : null}
      <ChipGroup title="游戏模式">
        {BF1_MODES.map((m) => (
          <Chip
            key={m.code}
            selected={filters.modes.includes(m.code)}
            onClick={() => patch({ modes: toggle(filters.modes, m.code) })}
          >
            {m.label}
          </Chip>
        ))}
      </ChipGroup>
      <ChipGroup title="区域">
        {BF1_REGIONS.map((r) => (
          <Chip
            key={r.code}
            selected={filters.regions.includes(r.code)}
            onClick={() => patch({ regions: toggle(filters.regions, r.code) })}
          >
            {r.label}
          </Chip>
        ))}
      </ChipGroup>
      <ChipGroup title="空位">
        {EMPTY_SLOT_OPTIONS.map((o) => (
          <Chip
            key={o.id}
            selected={filters.emptySlots.includes(o.id)}
            onClick={() => patch({ emptySlots: toggle(filters.emptySlots, o.id) })}
          >
            {o.label}
          </Chip>
        ))}
      </ChipGroup>
      <ChipGroup title="服务器规模">
        {SIZE_OPTIONS.map((n) => (
          <Chip
            key={n}
            selected={filters.sizes.includes(n)}
            onClick={() => patch({ sizes: toggle(filters.sizes, n) })}
          >
            {n} 人
          </Chip>
        ))}
      </ChipGroup>
      <ChipGroup title="地图">
        {BF1_MAPS.map((m) => (
          <Chip
            key={m.code}
            selected={filters.maps.includes(m.code)}
            onClick={() => patch({ maps: toggle(filters.maps, m.code) })}
          >
            {m.label}
          </Chip>
        ))}
      </ChipGroup>
      <ChipGroup title="空服">
        <Chip
          selected={filters.includeEmpty}
          onClick={() => patch({ includeEmpty: !filters.includeEmpty })}
        >
          包含 0 人服务器
        </Chip>
        <p className="w-full text-xs text-white/40">EA 抽样返回，结果不全</p>
      </ChipGroup>
      {options ? (
        <section>
          <h3 className="mb-1 text-[13px] font-medium text-white/55">更多玩法设置</h3>
          <RuleGroups ui={ui} large />
        </section>
      ) : null}
    </div>
  );
}

function ChipGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2.5 text-[13px] font-medium text-white/55">{title}</h3>
      <div className="flex flex-wrap gap-2">{children}</div>
    </section>
  );
}

function Chip({
  selected,
  onClick,
  count,
  large,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  /** 选上后的结果数；为 0 且未选中时置灰 */
  count?: number;
  /** 手机抽屉里的主要选项用 44px 触控高度 */
  large?: boolean;
  children: React.ReactNode;
}) {
  const empty = count === 0 && !selected;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "compact-action inline-flex items-center gap-1.5 rounded-sm border px-3 text-sm transition-colors",
        large ? "h-11" : "h-9",
        selected
          ? "border-amber-400/70 bg-amber-400/15 text-amber-200"
          : empty
            ? "border-white/8 text-white/30"
            : "border-white/12 bg-white/[0.03] text-white/75 hover:bg-white/8 active:bg-white/10",
      )}
    >
      {children}
      {count !== undefined ? (
        <span
          className={cn("text-xs tabular-nums", selected ? "text-amber-200/70" : "text-white/35")}
        >
          {count}
        </span>
      ) : null}
    </button>
  );
}

function PanelTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="border-b border-white/10 pb-2 text-xs font-semibold tracking-[0.18em] text-white/55 uppercase">
      {children}
    </h2>
  );
}

/** 可折叠筛选分区：标题行点击展开/收起，选中数以琥珀色角标提示 */
function FilterSection({
  title,
  count,
  defaultOpen,
  scroll = true,
  children,
}: {
  title: string;
  count: number;
  defaultOpen?: boolean;
  /** 展开后限高内部滚动；手机抽屉里关掉，免得滚动套滚动 */
  scroll?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div className="border-b border-white/10">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between py-2.5 text-sm text-white/80 transition-colors hover:text-white"
      >
        <span>
          {title}
          {count > 0 ? <span className="ml-1.5 text-xs text-amber-300">{count}</span> : null}
        </span>
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div className={cn("pb-2", scroll && "max-h-72 overflow-y-auto")}>{children}</div>
      ) : null}
    </div>
  );
}

/** 游戏式复选框：方框 + 右侧标签，选中为白底黑勾，复刻 BF1 筛选勾选样式 */
function GameCheckbox({
  checked,
  onChange,
  label,
  count,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  /** 选上后的结果数；为 0 且未选中时置灰 */
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      aria-pressed={checked}
      className={cn(
        "flex w-full items-center gap-2.5 py-1 text-left text-sm transition-colors hover:text-white",
        count === 0 && !checked ? "text-white/30" : "text-white/75",
      )}
    >
      <span
        className={cn(
          "flex size-4 shrink-0 items-center justify-center border transition-colors",
          checked ? "border-white bg-white" : "border-white/40 bg-transparent",
        )}
      >
        {checked ? <Check className="size-3 text-black" strokeWidth={3} /> : null}
      </span>
      <span className="truncate">{label}</span>
      <CountBadge count={count} />
    </button>
  );
}
