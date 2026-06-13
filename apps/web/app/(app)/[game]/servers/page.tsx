"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Lock, MapPin, RotateCw, Users } from "lucide-react";
import { DarkInput } from "@/components/common/DarkInput";
import { CountryFlag } from "@/components/common/CountryFlag";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ServerListSkeleton } from "@/components/layout/PageSkeleton";
import { pingSiteLabel, pingSiteCountry } from "@/lib/bf1/pingsite";
import {
  BF1_MAPS,
  BF1_MODES,
  BF1_REGIONS,
  mapLabel,
  modeLabel,
  regionLabel,
} from "@/lib/bf1/catalog";
import { bf1Api, type ServerSummary } from "@/lib/api/bf1";

const PAGE_SIZE = 50;

/** 服务器规模（最大人数）固定档位，复刻游戏「遊戲規模」筛选项 */
const SIZE_OPTIONS = [10, 16, 24, 32, 40, 48, 64];

/** 空位（剩余席位）分档，复刻游戏「空位」筛选项 */
const EMPTY_SLOT_OPTIONS: { id: string; label: string }[] = [
  { id: "none", label: "无" },
  { id: "1-5", label: "1-5" },
  { id: "6-10", label: "6-10" },
  { id: "10+", label: "10+" },
];

interface FilterState {
  modes: string[]; // game_mode 代号
  maps: string[]; // map_name 代号
  regions: string[]; // region 代号
  emptySlots: string[]; // EMPTY_SLOT_OPTIONS.id
  sizes: number[]; // max_player_count 档位
  nameFilter: string; // 结果内按名称二次筛选
}

const DEFAULT_FILTERS: FilterState = {
  modes: [],
  maps: [],
  regions: [],
  emptySlots: [],
  sizes: [],
  nameFilter: "",
};

/** 剩余席位分档 id；无人数上限的服务器归入空串（不参与分档筛选） */
function emptyBucket(s: ServerSummary): string {
  if (s.max_player_count <= 0) return "";
  const free = s.max_player_count - s.player_count;
  if (free <= 0) return "none";
  if (free <= 5) return "1-5";
  if (free <= 10) return "6-10";
  return "10+";
}

function toggle<T>(arr: T[], val: T): T[] {
  return arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val];
}

/** 防抖取值：value 停止变化 delayMs 后才返回新值，用于把高频筛选改动合并为一次请求 */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export default function ServerListPage() {
  const params = useParams<{ game: string }>();
  const router = useRouter();
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);

  // 地图 / 模式 / 区域 / 规模四个维度下推到后端由 EA 按条件检索：勾选即作为查询参数触发新
  // 请求，而非仅在已加载的前若干条结果内过滤，避免冷门条件被结果上限截断而漏掉真实存在的服务器。
  // 勾选合并 300ms 防抖，避免连续勾选产生多次 EA 请求；排序保证勾选顺序不同不产生多份缓存。
  const selection = useMemo(
    () => ({
      maps: [...filters.maps].sort(),
      modes: [...filters.modes].sort(),
      regions: [...filters.regions].sort(),
      sizes: [...filters.sizes].sort((a, b) => a - b),
    }),
    [filters.maps, filters.modes, filters.regions, filters.sizes],
  );
  const debouncedSelection = useDebouncedValue(selection, 300);
  // 名称同样下推到 EA（包含匹配、大小写不敏感）以补全前若干条之外的同名服务器，打字停止
  // 450ms 后才请求；同时下方 filtered 用即时 nameFilter 对当前结果二次过滤，保证打字即时反馈。
  const debouncedName = useDebouncedValue(filters.nameFilter.trim(), 450);

  const servers = useQuery({
    queryKey: ["bf1-servers", debouncedSelection, debouncedName],
    queryFn: () =>
      bf1Api.listServers({
        name: debouncedName || undefined,
        maps: debouncedSelection.maps.length ? debouncedSelection.maps : undefined,
        modes: debouncedSelection.modes.length ? debouncedSelection.modes : undefined,
        regions: debouncedSelection.regions.length ? debouncedSelection.regions : undefined,
        sizes: debouncedSelection.sizes.length ? debouncedSelection.sizes : undefined,
        limit: 500,
      }),
    // 刷新 / 切换筛选期间保留上一次结果，避免请求期间 servers.data 变 undefined 导致列表与筛选面板闪断。
    placeholderData: keepPreviousData,
  });

  // servers.data 为 undefined 时回落空数组；包进 useMemo 保持引用稳定，
  // 避免每次 render 生成新数组导致下游 filtered useMemo 失效（exhaustive-deps）。
  const allItems = useMemo(() => servers.data?.items ?? [], [servers.data?.items]);

  // 服务端已按地图 / 模式 / 区域 / 规模 / 名称检索，这里只做 EA 无法下推的二次过滤：
  // 空位是实时人数状态、EA searchServers 不支持按其过滤；名称做即时包含过滤以提供打字反馈。
  const filtered = useMemo(() => {
    const nameNeedle = filters.nameFilter.trim().toLowerCase();
    return allItems.filter((s) => {
      if (filters.emptySlots.length && !filters.emptySlots.includes(emptyBucket(s))) return false;
      if (nameNeedle && !s.name.toLowerCase().includes(nameNeedle)) return false;
      return true;
    });
  }, [allItems, filters.emptySlots, filters.nameFilter]);

  const sorted = useMemo(
    () => [...filtered].sort((a, b) => b.player_count - a.player_count),
    [filtered],
  );

  const visibleItems = sorted.slice(0, visibleCount);
  const hasMore = visibleCount < sorted.length;
  const filtersActive =
    filters.modes.length > 0 ||
    filters.maps.length > 0 ||
    filters.regions.length > 0 ||
    filters.emptySlots.length > 0 ||
    filters.sizes.length > 0 ||
    filters.nameFilter.trim().length > 0;

  const resetFilters = () => {
    setFilters(DEFAULT_FILTERS);
    setVisibleCount(PAGE_SIZE);
  };
  const patch = (p: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...p }));
    setVisibleCount(PAGE_SIZE);
  };

  // 顶部「筛选条件」摘要：当前生效条件概览，复刻游戏标题行右侧
  const summaryChips: string[] = [
    ...filters.modes.map(modeLabel),
    ...filters.maps.map(mapLabel),
    ...filters.regions.map(regionLabel),
    ...filters.emptySlots.map((id) => EMPTY_SLOT_OPTIONS.find((o) => o.id === id)?.label ?? id),
    ...filters.sizes.map((n) => `${n} 人`),
    ...(filters.nameFilter.trim() ? [`名称含「${filters.nameFilter.trim()}」`] : []),
  ];

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
              {summaryChips.length ? summaryChips.join("、") : "无"}
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

      {/* 子标签：复刻游戏「遊戲 / 我的最愛 / 最近遊玩 / 您的伺服器」。
          后三者依赖玩家账号维度的收藏 / 历史 / 自有服务器数据，本应用暂未接入，置灰不可点。 */}
      <SubTabs />

      {/* 主体：左密集表格 + 右筛选面板。桌面端整块填满剩余高度，仅列表内部滚动 */}
      <div className="grid grid-cols-1 gap-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="flex min-w-0 flex-col lg:min-h-0">
          {servers.isLoading ? (
            <ServerListSkeleton />
          ) : sorted.length > 0 ? (
            <>
              {/* 表头常驻，不随列表滚动 */}
              <div className="flex items-center gap-4 border-b border-white/10 px-3 pb-2 text-[11px] font-semibold tracking-[0.16em] text-white/40 uppercase lg:shrink-0">
                <span className="flex-1">名称</span>
                <span className="w-28 text-right">玩家</span>
                <span className="hidden w-24 text-right sm:block">节点</span>
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
                      onClick={() =>
                        s.game_id && router.push(`/${params.game}/server/${s.game_id}`)
                      }
                    />
                  ))}
                </ul>
                <div className="flex flex-col items-center gap-2 pt-4 text-sm text-white/45">
                  <span className="tabular-nums">
                    已显示 {visibleItems.length} / {sorted.length} 条
                    {filtersActive ? `（共 ${allItems.length} 条，已筛选）` : null}
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
            <div className="rounded-sm border border-dashed border-white/15 py-16 text-center text-sm text-white/45">
              {filtersActive ? "当前筛选条件下没有匹配的服务器" : "未找到匹配的服务器"}
            </div>
          )}
        </section>

        {/* 筛选面板常驻，复刻游戏右侧固定筛选栏；自身满高，条目过多时仅面板内部滚动 */}
        <FilterPanel
          filters={filters}
          patch={patch}
          reset={resetFilters}
          filtersActive={filtersActive}
          summaryChips={summaryChips}
        />
      </div>
    </main>
  );
}

/* ----------------------------- 子标签 ----------------------------- */

function SubTabs() {
  const tabs = [
    { label: "游戏", active: true, enabled: true },
    { label: "我的最爱", active: false, enabled: false },
    { label: "最近游玩", active: false, enabled: false },
    { label: "您的服务器", active: false, enabled: false },
  ];
  return (
    <nav className="flex items-center gap-6 border-b border-white/10 pb-2 text-sm lg:shrink-0">
      {tabs.map((t) => (
        <span
          key={t.label}
          title={t.enabled ? undefined : "需玩家账号维度数据，暂未接入"}
          className={cn(
            "relative font-medium tracking-wide",
            t.active
              ? "text-white"
              : t.enabled
                ? "cursor-pointer text-white/55 hover:text-white"
                : "cursor-default text-white/30",
          )}
        >
          {t.label}
          {t.active ? (
            <span className="absolute -bottom-2 left-0 h-0.5 w-full bg-amber-400" />
          ) : null}
        </span>
      ))}
    </nav>
  );
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
        className="group flex w-full items-center gap-4 border-b border-white/[0.06] px-3 py-2.5 text-left transition-colors hover:bg-white/[0.06]"
      >
        {/* 地图缩略图 */}
        <div className="relative h-14 w-24 shrink-0 overflow-hidden rounded-sm bg-white/[0.04]">
          {server.map_image_url ? (
            // EA CDN 自带缩放与缓存，不走 next/image
            // eslint-disable-next-line @next/next/no-img-element
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
            {modeLabel ? <span>{modeLabel}</span> : null}
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
        <div className="flex w-28 shrink-0 items-center justify-end gap-1.5 text-sm whitespace-nowrap tabular-nums">
          <Users className="size-3.5 text-white/35" />
          <span className={cn(fill >= 100 ? "text-amber-300" : "text-white")}>
            {server.player_count}
          </span>
          <span className="text-white/40">/ {server.max_player_count}</span>
          {server.queue_count > 0 ? (
            <span className="text-white/45">[{server.queue_count}]</span>
          ) : null}
        </div>

        {/* 节点（数据中心）：EA 不返回 ping 数值，展示节点城市，对应游戏内 ping 所测目标 */}
        <div className="hidden w-24 shrink-0 justify-end text-right text-xs text-white/55 sm:flex">
          <span className="truncate" title={server.ping_site ?? undefined}>
            {node ?? "—"}
          </span>
        </div>
      </button>
    </li>
  );
}

/* ----------------------------- 右侧筛选面板 ----------------------------- */

function FilterPanel({
  filters,
  patch,
  reset,
  filtersActive,
  summaryChips,
}: {
  filters: FilterState;
  patch: (p: Partial<FilterState>) => void;
  reset: () => void;
  filtersActive: boolean;
  summaryChips: string[];
}) {
  return (
    <aside className="space-y-5 lg:min-h-0 lg:self-stretch lg:overflow-y-auto lg:pr-1">
      {/* 您的筛选条件：当前生效条件的标签集 */}
      <section>
        <PanelTitle>您的筛选条件</PanelTitle>
        {summaryChips.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {summaryChips.map((c) => (
              <span key={c} className="rounded-sm bg-white/8 px-2 py-1 text-xs text-white/70">
                {c}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-xs text-white/35">未设置筛选条件</p>
        )}
      </section>

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
        </div>
      </section>

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
  children,
}: {
  title: string;
  count: number;
  defaultOpen?: boolean;
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
      {open ? <div className="max-h-72 overflow-y-auto pb-2">{children}</div> : null}
    </div>
  );
}

/** 游戏式复选框：方框 + 右侧标签，选中为白底黑勾，复刻 BF1 筛选勾选样式 */
function GameCheckbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      className="flex w-full items-center gap-2.5 py-1 text-left text-sm text-white/75 transition-colors hover:text-white"
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
    </button>
  );
}
