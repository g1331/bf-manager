"use client";

import { useMemo, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search, Users, Lock, Filter, X } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/PageHeader";
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

export default function ServerListPage() {
  const params = useParams<{ game: string }>();
  const router = useRouter();
  const [keyword, setKeyword] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortKey>("players_desc");
  const [showFilters, setShowFilters] = useState(false);

  const servers = useQuery({
    queryKey: ["bf1-servers", activeQuery],
    queryFn: () => bf1Api.listServers(activeQuery || undefined, 500),
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

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeader kicker="Servers" title="服务器列表" description="浏览所有 Battlefield 1 服务器" />

      <form onSubmit={submit} className="flex gap-2">
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="按服务器名搜索（留空查全部）"
          className="flex-1"
        />
        <Button type="submit" disabled={servers.isFetching} size="lg" className="px-6">
          <Search className="size-4" />
          {servers.isFetching ? "查询中…" : "搜索"}
        </Button>
      </form>

      {allItems.length > 0 ? (
        <FilterBar
          show={showFilters}
          onToggle={() => setShowFilters((v) => !v)}
          filters={filters}
          patch={patchFilters}
          reset={resetFilters}
          filtersActive={filtersActive}
          regionCodes={regionCodes}
          modeCodes={modeCodes}
          allItems={allItems}
          sort={sort}
          setSort={setSort}
        />
      ) : null}

      {servers.isLoading ? (
        <div className="text-muted-foreground p-12 text-center">加载中…</div>
      ) : sorted.length > 0 ? (
        <>
          <section className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {visibleItems.map((s) => (
              <ServerCard
                key={s.server_id}
                server={s}
                onClick={() => s.game_id && router.push(`/${params.game}/server/${s.game_id}`)}
              />
            ))}
          </section>
          <div className="text-muted-foreground flex flex-col items-center gap-2 pt-2 text-sm">
            <span className="tabular-nums">
              已显示 {visibleItems.length} / {sorted.length} 条
              {filtersActive ? `（共 ${allItems.length} 条，已筛选）` : null}
            </span>
            {hasMore ? (
              <Button
                variant="outline"
                onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                className="px-8"
              >
                加载更多
              </Button>
            ) : null}
          </div>
        </>
      ) : (
        <div className="text-muted-foreground rounded-lg border border-dashed p-12 text-center">
          {servers.data
            ? filtersActive
              ? "当前筛选条件下没有匹配的服务器"
              : "未找到匹配的服务器"
            : "请先发起搜索"}
        </div>
      )}
    </main>
  );
}

function FilterBar({
  show,
  onToggle,
  filters,
  patch,
  reset,
  filtersActive,
  regionCodes,
  modeCodes,
  allItems,
  sort,
  setSort,
}: {
  show: boolean;
  onToggle: () => void;
  filters: FilterState;
  patch: (p: Partial<FilterState>) => void;
  reset: () => void;
  filtersActive: boolean;
  regionCodes: string[];
  modeCodes: string[];
  allItems: ServerSummary[];
  sort: SortKey;
  setSort: (s: SortKey) => void;
}) {
  return (
    <section className="rounded-lg border">
      <div className="flex flex-wrap items-center gap-2 p-3">
        <Button type="button" variant="outline" size="sm" onClick={onToggle} className="gap-1">
          <Filter className="size-4" />
          筛选
          {filtersActive ? <span className="bg-foreground size-1.5 rounded-full" /> : null}
        </Button>
        <SelectField
          ariaLabel="排序方式"
          value={sort}
          onChange={(v) => setSort(v as SortKey)}
          options={SORT_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        {filtersActive ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={reset}
            className="ml-auto gap-1 text-xs"
          >
            <X className="size-3" />
            清除筛选
          </Button>
        ) : null}
      </div>
      {show ? (
        <div className="grid grid-cols-1 gap-3 border-t p-3 sm:grid-cols-2 lg:grid-cols-3">
          <LabeledField label="地区">
            <SelectField
              ariaLabel="按地区筛选"
              value={filters.region}
              onChange={(v) => patch({ region: v })}
              options={[
                { value: "", label: "全部地区" },
                ...regionCodes.map((c) => ({
                  value: c,
                  label: optionLabel(allItems, "region", c),
                })),
              ]}
            />
          </LabeledField>
          <LabeledField label="模式">
            <SelectField
              ariaLabel="按模式筛选"
              value={filters.mode}
              onChange={(v) => patch({ mode: v })}
              options={[
                { value: "", label: "全部模式" },
                ...modeCodes.map((c) => ({ value: c, label: optionLabel(allItems, "mode", c) })),
              ]}
            />
          </LabeledField>
          <LabeledField label="最少人数">
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
            />
          </LabeledField>
          <fieldset className="flex flex-wrap gap-x-4 gap-y-2 text-sm sm:col-span-2 lg:col-span-3">
            <CheckboxField
              checked={filters.hidePassword}
              onChange={(v) => patch({ hidePassword: v })}
              label="隐藏密码服"
            />
            <CheckboxField
              checked={filters.onlyOfficial}
              onChange={(v) => patch({ onlyOfficial: v })}
              label="仅官方"
            />
            <CheckboxField
              checked={filters.onlyRanked}
              onChange={(v) => patch({ onlyRanked: v })}
              label="仅 Ranked"
            />
            <CheckboxField
              checked={filters.hideFull}
              onChange={(v) => patch({ hideFull: v })}
              label="隐藏满员"
            />
          </fieldset>
        </div>
      ) : null}
    </section>
  );
}

function LabeledField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-muted-foreground text-xs">{label}</span>
      {children}
    </label>
  );
}

function SelectField({
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
      className="border-input bg-background ring-offset-background focus-visible:ring-ring h-9 rounded-md border px-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function CheckboxField({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="border-input size-4 rounded"
      />
      <span>{label}</span>
    </label>
  );
}

function ServerCard({ server, onClick }: { server: ServerSummary; onClick: () => void }) {
  const fill =
    server.max_player_count > 0
      ? Math.round((server.player_count / server.max_player_count) * 100)
      : 0;
  const mapLabel = server.map_display_name ?? server.map_name;
  const modeLabel = server.mode_display_name ?? server.game_mode;
  const regionLabel = server.region_display_name ?? server.region;
  return (
    <Card
      onClick={onClick}
      className="group hover:border-primary active:bg-muted/50 cursor-pointer transition"
    >
      <CardContent className="flex gap-3 p-4">
        {server.map_image_url ? (
          <div className="bg-muted relative h-20 w-32 shrink-0 overflow-hidden rounded">
            {/* EA CDN（eaassets-a.akamaihd.net）已自带缩放与缓存，不走 next/image
                以避免多套一层 Next 优化代理；如未来开启 next/image，需要在
                next.config.js 的 images.remotePatterns 加 EA CDN 白名单。 */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={server.map_image_url}
              alt={mapLabel ?? ""}
              loading="lazy"
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
          </div>
        ) : null}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex items-start justify-between gap-2">
            <h3 className="line-clamp-2 flex-1 font-medium" title={server.name}>
              {server.name}
            </h3>
            {server.has_password ? (
              <Lock className="text-muted-foreground size-4 shrink-0" />
            ) : null}
          </div>
          <div className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {mapLabel ? <span>{mapLabel}</span> : null}
            {modeLabel ? <span>· {modeLabel}</span> : null}
            {regionLabel ? <span>· {regionLabel}</span> : null}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 text-sm tabular-nums">
              <Users className="text-muted-foreground size-4" />
              <span className="font-medium">{server.player_count}</span>
              <span className="text-muted-foreground">/ {server.max_player_count}</span>
              {server.queue_count > 0 ? (
                <span className="text-muted-foreground">+{server.queue_count}</span>
              ) : null}
            </div>
            <div className="bg-muted relative h-1.5 flex-1 overflow-hidden rounded-full">
              <div
                className="bg-foreground/45 absolute inset-y-0 left-0 transition-all"
                style={{ width: `${Math.min(fill, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
