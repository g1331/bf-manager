"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { EquipmentFilterBar } from "@/components/bf1/EquipmentFilterBar";
import { RarityStar } from "@/components/bf1/visual/RarityStar";
import { RowsSkeleton } from "@/components/layout/PageSkeleton";
import {
  rarityByKills,
  rarityByStars,
  rarityHex,
  skinRarityFromName,
  skinRarityHex,
  starsByKills,
} from "@/lib/bf1/rarity";
import { cn } from "@/lib/utils";
import { Panel } from "./CareerOverview";

interface GearItem {
  name: string | null;
  category: string | null;
  kills: number | null;
  time_seconds: number | null;
  image: string | null;
  skin_name: string | null;
  skin_rarity: string | null;
  skin_image: string | null;
}

/** 击杀和时长都为 0 视为没用过 */
export function isUsed(item: { kills: number | null; time_seconds: number | null }): boolean {
  return (item.kills ?? 0) > 0 || (item.time_seconds ?? 0) > 0;
}

export interface GearColumn<T> {
  key: string;
  label: string;
  value: (item: T) => number | null;
  format: (value: number | null) => string;
}

/**
 * 武器 / 载具排行：名称与分类过滤、按任一数据列排序（再点一次反向），
 * 默认隐藏击杀与时长都为 0 的条目——BF1 武器全集两百多把，多数玩家大半没碰过。
 */
export function EquipmentTable<T extends GearItem>({
  items,
  loading,
  columns,
  placeholder,
  emptyText,
}: {
  items: T[];
  loading: boolean;
  columns: GearColumn<T>[];
  placeholder: string;
  emptyText: string;
}) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [showUnused, setShowUnused] = useState(false);
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({
    key: columns[0].key,
    desc: true,
  });

  const used = useMemo(() => items.filter(isUsed), [items]);
  const pool = showUnused ? items : used;
  const categories = useMemo(
    () => [...new Set(pool.map((i) => i.category).filter((c): c is string => !!c))],
    [pool],
  );

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const col = columns.find((c) => c.key === sort.key) ?? columns[0];
    // 缺失值始终排在最后，不随升降序翻转
    const val = (i: T) => col.value(i);
    return pool
      .filter(
        (i) =>
          (category == null || i.category === category) &&
          (!q ||
            (i.name ?? "").toLowerCase().includes(q) ||
            (i.skin_name ?? "").toLowerCase().includes(q)),
      )
      .sort((a, b) => {
        const va = val(a);
        const vb = val(b);
        if (va == null) return vb == null ? 0 : 1;
        if (vb == null) return -1;
        return sort.desc ? vb - va : va - vb;
      });
  }, [pool, columns, sort, category, search]);

  const onSort = (key: string) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: true }));

  if (loading) return <RowsSkeleton rows={8} />;
  if (items.length === 0)
    return (
      <Panel>
        <div className="py-8 text-center text-sm text-white/40">{emptyText}</div>
      </Panel>
    );

  return (
    <Panel className="@container">
      <EquipmentFilterBar
        categories={categories}
        selected={categories.includes(category ?? "") ? category : null}
        onSelect={setCategory}
        search={search}
        onSearch={setSearch}
        placeholder={placeholder}
      />

      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 text-white/45">排序</span>
          {columns.map((c) => {
            const active = sort.key === c.key;
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => onSort(c.key)}
                className={cn(
                  "flex items-center gap-0.5 px-2 py-1 transition-colors",
                  active ? "bg-amber-400/15 text-amber-300" : "text-white/55 hover:text-white",
                )}
              >
                {c.label}
                {active ? (
                  sort.desc ? (
                    <ArrowDown className="size-3" />
                  ) : (
                    <ArrowUp className="size-3" />
                  )
                ) : null}
              </button>
            );
          })}
        </div>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-white/55 select-none">
          <input
            type="checkbox"
            checked={showUnused}
            onChange={(e) => setShowUnused(e.target.checked)}
            className="accent-amber-400"
          />
          显示未使用（{items.length - used.length}）
        </label>
      </div>

      {rows.length === 0 ? (
        <div className="py-8 text-center text-sm text-white/40">无匹配结果</div>
      ) : (
        <ol className="divide-y divide-white/[0.06]">
          {rows.map((it, i) => (
            <GearRow
              // EA 返回里存在同名条目（如 繃帶包 在多个兵种组重复出现），单用 name 作 key 会重复
              key={`${it.name ?? ""}-${it.category ?? ""}-${i}`}
              rank={i + 1}
              item={it}
              columns={columns}
              sortKey={sort.key}
            />
          ))}
        </ol>
      )}
    </Panel>
  );
}

function GearRow<T extends GearItem>({
  rank,
  item,
  columns,
  sortKey,
}: {
  rank: number;
  item: T;
  columns: GearColumn<T>[];
  sortKey: string;
}) {
  const stars = starsByKills(item.kills);
  const image = item.skin_image ?? item.image;
  return (
    <li className="grid grid-cols-[2rem_6rem_minmax(0,1fr)] items-center gap-x-3 gap-y-2 py-3 @3xl:grid-cols-[2rem_8rem_minmax(0,1fr)_auto]">
      <span
        className={cn(
          "font-display text-center text-sm font-bold tabular-nums",
          rank <= 3 ? "text-amber-400" : "text-white/30",
        )}
      >
        {rank}
      </span>
      <div className="flex h-12 items-center justify-center bg-gradient-to-br from-white/[0.07] to-transparent @3xl:h-14">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={image}
            alt=""
            loading="lazy"
            className="max-h-full max-w-full object-contain p-1"
          />
        ) : null}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="truncate font-semibold"
            style={{ color: rarityHex[rarityByKills(item.kills)] }}
            title={item.name ?? ""}
          >
            {item.name ?? "—"}
          </span>
          {stars > 0 ? (
            <span className="flex shrink-0 items-center gap-0.5 text-xs font-bold text-white/80 tabular-nums">
              <RarityStar rarity={rarityByStars(stars)} size={13} />
              {stars}
            </span>
          ) : null}
        </div>
        <div className="truncate text-[11px] text-white/45">
          {item.skin_name ? (
            <span style={{ color: skinRarityHex[skinRarityFromName(item.skin_rarity)] }}>
              {item.skin_name}
              <span className="text-white/25"> · </span>
            </span>
          ) : null}
          {item.category}
        </div>
      </div>
      {/* 宽容器一行排开，窄容器折到图片下方 */}
      <dl className="col-span-full flex flex-wrap gap-x-5 gap-y-1 pl-11 @3xl:col-span-1 @3xl:flex-nowrap @3xl:gap-x-0 @3xl:pl-0">
        {columns.map((c) => (
          <div
            key={c.key}
            className="flex items-baseline gap-1.5 @3xl:w-20 @3xl:flex-col @3xl:items-end @3xl:gap-0"
          >
            <dt className="text-[11px] text-white/40">{c.label}</dt>
            <dd
              className={cn(
                "text-sm tabular-nums",
                sortKey === c.key ? "font-bold text-amber-300" : "text-white/85",
              )}
            >
              {c.format(c.value(item))}
            </dd>
          </div>
        ))}
      </dl>
    </li>
  );
}
