"use client";

import { useMemo, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Search, Users, Lock, RotateCw, MapPin } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { pingSiteLabel } from "@/lib/bf1/pingsite";
import { bf1Api, type ServerSummary } from "@/lib/api/bf1";

const PAGE_SIZE = 50;

type SortKey = "players_desc" | "players_asc" | "fill_desc" | "name_asc";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "players_desc", label: "人数从高到低" },
  { value: "players_asc", label: "人数从低到高" },
  { value: "fill_desc", label: "满员率从高到低" },
  { value: "name_asc", label: "名称 A→Z" },
];

interface FilterState {
  region: string;
  mode: string;
  minPlayers: number;
  hidePassword: boolean;
  onlyOfficial: boolean;
  onlyRanked: boolean;
  hideFull: boolean;
}

const DEFAULT_FILTERS: FilterState = {
  region: "",
  mode: "",
  minPlayers: 0,
  hidePassword: false,
  onlyOfficial: false,
  onlyRanked: false,
  hideFull: false,
};

function fillRate(s: ServerSummary): number {
  return s.max_player_count > 0 ? s.player_count / s.max_player_count : 0;
}

function uniqueOptions(items: ServerSummary[], key: "region" | "mode"): string[] {
  const map = new Map<string, string>();
  for (const s of items) {
    if (key === "region") {
      const code = s.region;
      if (!code) continue;
      map.set(code, s.region_display_name ?? code);
    } else {
      const code = s.game_mode;
      if (!code) continue;
      map.set(code, s.mode_display_name ?? code);
    }
  }
  return Array.from(map.entries())
    .sort((a, b) => a[1].localeCompare(b[1], "zh-Hans"))
    .map(([code]) => code);
}

function optionLabel(items: ServerSummary[], key: "region" | "mode", code: string): string {
  for (const s of items) {
    if (key === "region" && s.region === code) return s.region_display_name ?? code;
    if (key === "mode" && s.game_mode === code) return s.mode_display_name ?? code;
  }
  return code;
}

/** ISO 3166-1 alpha-2 国家代码 → 国旗 emoji（区域指示符）；非两位字母返回 null */
function flagEmoji(cc: string | null): string | null {
  if (!cc || cc.length !== 2) return null;
  const base = 0x1f1e6;
  const codePoints = cc
    .toUpperCase()
    .split("")
    .map((c) => base + (c.charCodeAt(0) - 65));
  if (codePoints.some((n) => n < base || n > base + 25)) return null;
  return String.fromCodePoint(...codePoints);
}

export default function ServerListPage() {
  const params = useParams<{ game: string }>();
  const router = useRouter();
  const [keyword, setKeyword] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortKey>("players_desc");

  const servers = useQuery({
    queryKey: ["bf1-servers", activeQuery],
    queryFn: () => bf1Api.listServers(activeQuery || undefined, 500),
    // 重新搜索（activeQuery 变化）时保留上一次结果，避免请求期间 servers.data 变 undefined
    // 导致筛选面板（依赖 allItems.length > 0）与列表整体闪断消失。
    placeholderData: keepPreviousData,
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setActiveQuery(keyword.trim());
    setVisibleCount(PAGE_SIZE);
  };

  const allItems = servers.data?.items ?? [];
  const regionCodes = useMemo(() => uniqueOptions(allItems, "region"), [allItems]);
  const modeCodes = useMemo(() => uniqueOptions(allItems, "mode"), [allItems]);

  const filtered = useMemo(() => {
    return allItems.filter((s) => {
      if (filters.region && s.region !== filters.region) return false;
      if (filters.mode && s.game_mode !== filters.mode) return false;
      if (filters.minPlayers > 0 && s.player_count < filters.minPlayers) return false;
      if (filters.hidePassword && s.has_password) return false;
      if (filters.onlyOfficial && !s.is_official) return false;
      if (filters.onlyRanked && !s.is_ranked) return false;
      if (filters.hideFull && s.player_count >= s.max_player_count && s.max_player_count > 0) {
        return false;
      }
      return true;
    });
  }, [allItems, filters]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    switch (sort) {
      case "players_desc":
        arr.sort((a, b) => b.player_count - a.player_count);
        break;
      case "players_asc":
        arr.sort((a, b) => a.player_count - b.player_count);
        break;
      case "fill_desc":
        arr.sort((a, b) => fillRate(b) - fillRate(a));
        break;
      case "name_asc":
        arr.sort((a, b) => a.name.localeCompare(b.name, "zh-Hans"));
        break;
    }
    return arr;
  }, [filtered, sort]);

  const visibleItems = sorted.slice(0, visibleCount);
  const hasMore = visibleCount < sorted.length;
  const filtersActive =
    !!filters.region ||
    !!filters.mode ||
    filters.minPlayers > 0 ||
    filters.hidePassword ||
    filters.onlyOfficial ||
    filters.onlyRanked ||
    filters.hideFull;

  const resetFilters = () => {
    setFilters(DEFAULT_FILTERS);
    setVisibleCount(PAGE_SIZE);
  };
  const patchFilters = (patch: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
    setVisibleCount(PAGE_SIZE);
  };

  // 顶部「篩選條件」摘要：复刻游戏标题行右侧的当前生效条件概览
  const summaryChips: string[] = [];
  if (filters.region) summaryChips.push(optionLabel(allItems, "region", filters.region));
  if (filters.mode) summaryChips.push(optionLabel(allItems, "mode", filters.mode));
  if (filters.minPlayers > 0) summaryChips.push(`≥${filters.minPlayers} 人`);
  if (filters.hideFull) summaryChips.push("空位");
  if (filters.hidePassword) summaryChips.push("无密码");
  if (filters.onlyOfficial) summaryChips.push("官方");
  if (filters.onlyRanked) summaryChips.push("Ranked");
  if (activeQuery) summaryChips.push(`名称含「${activeQuery}」`);

  return (
    <main className="space-y-5 py-6 text-white">
      {/* 标题行：复刻游戏「伺服器瀏覽器」标题与右侧筛选摘要、刷新 */}
      <header className="flex flex-wrap items-end justify-between gap-3">
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
            <span className="text-white/75">
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

      <form onSubmit={submit} className="flex max-w-xl gap-2">
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="按服务器名搜索（留空查全部）"
          className="h-10 flex-1 border-white/15 bg-black/30 text-white placeholder:text-white/35"
        />
        {/* 搜索按钮沿用大厅控件风格：半透明深底 + 细边，而非高饱和填充色 */}
        <button
          type="submit"
          disabled={servers.isFetching}
          className="inline-flex h-10 shrink-0 items-center gap-2 rounded-sm border border-white/15 bg-white/[0.06] px-6 text-sm font-medium tracking-wide text-white/85 transition-colors hover:bg-white/[0.12] hover:text-white disabled:opacity-50"
        >
          <Search className="size-4" />
          {servers.isFetching ? "查询中…" : "搜索"}
        </button>
      </form>

      {/* 主体：左密集表格 + 右筛选面板，复刻游戏布局 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="min-w-0">
          {servers.isLoading ? (
            <div className="py-16 text-center text-sm text-white/45">加载中…</div>
          ) : sorted.length > 0 ? (
            <>
              {/* 列头 */}
              <div className="flex items-center gap-4 border-b border-white/10 px-3 pb-2 text-[11px] font-semibold tracking-[0.16em] text-white/40 uppercase">
                <span className="flex-1">名称</span>
                <span className="w-24 text-right">玩家</span>
                <span className="hidden w-24 text-right sm:block">节点</span>
              </div>
              <ul>
                {visibleItems.map((s) => (
                  <ServerRow
                    key={s.server_id}
                    server={s}
                    onClick={() => s.game_id && router.push(`/${params.game}/server/${s.game_id}`)}
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
            </>
          ) : (
            <div className="rounded-sm border border-dashed border-white/15 py-16 text-center text-sm text-white/45">
              {servers.data
                ? filtersActive
                  ? "当前筛选条件下没有匹配的服务器"
                  : "未找到匹配的服务器"
                : "请先发起搜索"}
            </div>
          )}
        </section>

        {/* 筛选面板常驻，复刻游戏右侧固定筛选栏；下拉选项在搜索返回数据后才填充 */}
        <FilterPanel
          filters={filters}
          patch={patchFilters}
          reset={resetFilters}
          filtersActive={filtersActive}
          regionCodes={regionCodes}
          modeCodes={modeCodes}
          allItems={allItems}
          sort={sort}
          setSort={setSort}
          summaryChips={summaryChips}
        />
      </div>
    </main>
  );
}

/* ----------------------------- 服务器表行 ----------------------------- */

function ServerRow({ server, onClick }: { server: ServerSummary; onClick: () => void }) {
  const mapLabel = server.map_display_name ?? server.map_name;
  const modeLabel = server.mode_display_name ?? server.game_mode;
  const flag = flagEmoji(server.country);
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
            {flag ? <span className="text-sm leading-none">{flag}</span> : null}
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

        {/* 玩家数 */}
        <div className="flex w-24 shrink-0 items-center justify-end gap-1.5 text-sm tabular-nums">
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
  regionCodes,
  modeCodes,
  allItems,
  sort,
  setSort,
  summaryChips,
}: {
  filters: FilterState;
  patch: (p: Partial<FilterState>) => void;
  reset: () => void;
  filtersActive: boolean;
  regionCodes: string[];
  modeCodes: string[];
  allItems: ServerSummary[];
  sort: SortKey;
  setSort: (s: SortKey) => void;
  summaryChips: string[];
}) {
  return (
    <aside className="space-y-5 lg:sticky lg:top-4 lg:self-start">
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

      {/* 快速筛选 */}
      <section className="space-y-3">
        <PanelTitle>快速筛选</PanelTitle>
        <PanelField label="地区">
          <PanelSelect
            ariaLabel="按地区筛选"
            value={filters.region}
            onChange={(v) => patch({ region: v })}
            options={[
              { value: "", label: "全部地区" },
              ...regionCodes.map((c) => ({ value: c, label: optionLabel(allItems, "region", c) })),
            ]}
          />
        </PanelField>
        <PanelField label="模式">
          <PanelSelect
            ariaLabel="按模式筛选"
            value={filters.mode}
            onChange={(v) => patch({ mode: v })}
            options={[
              { value: "", label: "全部模式" },
              ...modeCodes.map((c) => ({ value: c, label: optionLabel(allItems, "mode", c) })),
            ]}
          />
        </PanelField>
        <PanelField label="最少人数">
          <Input
            type="number"
            min={0}
            max={64}
            value={filters.minPlayers || ""}
            onChange={(e) => {
              const n = Number(e.target.value);
              patch({ minPlayers: Number.isFinite(n) && n > 0 ? n : 0 });
            }}
            placeholder="0"
            className="h-9 border-white/15 bg-black/30 text-white placeholder:text-white/35"
          />
        </PanelField>
        <PanelField label="排序">
          <PanelSelect
            ariaLabel="排序方式"
            value={sort}
            onChange={(v) => setSort(v as SortKey)}
            options={SORT_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          />
        </PanelField>
        <fieldset className="grid grid-cols-1 gap-2 pt-1 text-sm sm:grid-cols-2 lg:grid-cols-1">
          <PanelCheckbox
            checked={filters.hideFull}
            onChange={(v) => patch({ hideFull: v })}
            label="仅有空位"
          />
          <PanelCheckbox
            checked={filters.hidePassword}
            onChange={(v) => patch({ hidePassword: v })}
            label="隐藏密码服"
          />
          <PanelCheckbox
            checked={filters.onlyOfficial}
            onChange={(v) => patch({ onlyOfficial: v })}
            label="仅官方"
          />
          <PanelCheckbox
            checked={filters.onlyRanked}
            onChange={(v) => patch({ onlyRanked: v })}
            label="仅 Ranked"
          />
        </fieldset>
      </section>

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

function PanelField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-white/45">{label}</span>
      {children}
    </label>
  );
}

function PanelSelect({
  value,
  onChange,
  options,
  ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  ariaLabel: string;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-sm border border-white/15 bg-black/30 px-2 text-sm text-white focus-visible:ring-2 focus-visible:ring-amber-500/50 focus-visible:outline-none"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-neutral-900 text-white">
          {o.label}
        </option>
      ))}
    </select>
  );
}

function PanelCheckbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-white/75">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 rounded border-white/20 bg-black/30"
      />
      <span>{label}</span>
    </label>
  );
}
