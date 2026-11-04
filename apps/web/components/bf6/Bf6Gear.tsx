/**
 * 武器 / 载具 / 配备分区：带图的卡片网格，按击杀排，可按大类筛选。
 */
"use client";

import { useState, type ReactNode } from "react";
import type {
  Bf6GadgetStats,
  Bf6PlayerStats,
  Bf6VehicleStats,
  Bf6WeaponStats,
} from "@/lib/api/bf6";
import {
  GADGET_GROUPS,
  WEAPON_CATEGORIES,
  gadgetInfo,
  vehicleInfo,
  weaponInfo,
  type GadgetGroup,
  type VehicleGroup,
  type WeaponCategory,
} from "@/lib/bf6/catalog";
import { fmtCompact, fmtFixed, fmtHours, fmtInt, fmtKm, fmtPct, share } from "@/lib/bf6/format";
import { cn } from "@/lib/utils";
import { Empty } from "./Bf6Maps";
import { Bar, FilterChips } from "./primitives";

function GearCard({
  rank,
  tag,
  name,
  img,
  fadeRight,
  kills,
  topKills,
  mini,
  foot,
}: {
  rank: number;
  tag: string;
  name: string;
  img: string | null;
  /** 载具渲染图右侧常被裁掉，淡出边缘 */
  fadeRight?: boolean;
  kills: number | null;
  topKills: number;
  mini?: { label: string; value: string }[];
  foot: [ReactNode, ReactNode];
}) {
  return (
    <div className="border-bf6-line bg-bf6-panel hover:border-bf6-line-strong border px-3 pt-3 pb-3 transition-[border-color,transform] duration-200 hover:-translate-y-0.5 sm:px-4 sm:pt-3.5 sm:pb-4">
      <div className="text-bf6-mute flex items-center justify-between gap-2 text-[11px]">
        <span
          className={cn(
            "font-display text-[13px] tabular-nums",
            rank <= 3 ? "text-bf6" : "text-bf6-fg2",
          )}
        >
          #{String(rank).padStart(2, "0")}
        </span>
        <span className="truncate">{tag}</span>
      </div>
      <div className="relative -mx-2 my-0.5 h-[84px] bg-[radial-gradient(60%_70%_at_50%_55%,rgba(255,255,255,0.05),transparent_70%)] sm:h-[124px]">
        {img ? (
          <img
            src={img}
            alt=""
            loading="lazy"
            className={cn(
              "absolute inset-x-2 inset-y-1 h-[calc(100%-8px)] w-[calc(100%-16px)] object-contain drop-shadow-[0_10px_14px_rgba(0,0,0,0.55)]",
              fadeRight &&
                "[mask-image:linear-gradient(90deg,#000_72%,transparent_100%)] object-left",
            )}
          />
        ) : (
          <span className="font-display border-bf6-line-strong text-bf6-line-strong absolute inset-0 m-auto grid h-fit w-fit place-items-center border border-dashed px-5 py-4 text-xs tracking-[0.3em]">
            暂无图片
          </span>
        )}
      </div>
      <h4 className="font-display text-bf6-fg truncate text-lg leading-tight font-semibold sm:text-[22px]">
        {name}
      </h4>
      <div className="mt-2 flex items-baseline gap-1.5">
        <b className="font-display text-bf6-fg text-[22px] font-semibold tabular-nums sm:text-[28px]">
          {fmtInt(kills)}
        </b>
        <span className="text-bf6-mute text-xs">击杀</span>
      </div>
      <Bar ratio={share(kills, topKills)} className="mt-2" />
      {mini ? (
        <div className="border-bf6-line mt-3 grid grid-cols-3 gap-1.5 border-t pt-2.5">
          {mini.map((m) => (
            <div key={m.label} className="min-w-0">
              <span className="text-bf6-mute block text-[10px]">{m.label}</span>
              <b className="font-display text-bf6-fg block truncate text-sm font-medium tabular-nums sm:text-base">
                {m.value}
              </b>
            </div>
          ))}
        </div>
      ) : null}
      <div className="text-bf6-mute mt-2.5 flex justify-between gap-2 text-[11px]">
        <span className="truncate">{foot[0]}</span>
        <span className="truncate">{foot[1]}</span>
      </div>
    </div>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:gap-3.5 md:grid-cols-3 xl:grid-cols-4">
      {children}
    </div>
  );
}

function topKills(items: { kills: number | null }[]): number {
  return Math.max(1, ...items.map((i) => i.kills ?? 0));
}

/* ------------------------------ 武器 ------------------------------ */

type WeaponFilter = "all" | WeaponCategory;
const WEAPON_ORDER: WeaponCategory[] = ["ar", "crb", "smg", "mg", "dmr", "snp", "sg", "pst"];

export function WeaponsTab({ stats }: { stats: Bf6PlayerStats }) {
  const [filter, setFilter] = useState<WeaponFilter>("all");
  const weapons = stats.weapons;
  if (weapons.length === 0) return <Empty text="还没有武器记录" />;

  const counts = new Map<string, number>();
  weapons.forEach((w) => {
    const cat = weaponInfo(w.id).category;
    if (cat) counts.set(cat, (counts.get(cat) ?? 0) + 1);
  });
  const options = [
    { key: "all" as const, label: "全部", count: weapons.length },
    ...WEAPON_ORDER.filter((c) => counts.has(c)).map((c) => ({
      key: c,
      label: WEAPON_CATEGORIES[c].zh,
      count: counts.get(c) ?? 0,
    })),
  ];
  const top = topKills(weapons);
  const rows = weapons
    .map((w, i) => ({ w, rank: i + 1, info: weaponInfo(w.id) }))
    .filter(({ info }) => filter === "all" || info.category === filter);

  return (
    <div>
      <FilterChips options={options} value={filter} onChange={setFilter} />
      <Grid>
        {rows.map(({ w, rank, info }) => (
          <GearCard
            key={w.id}
            rank={rank}
            tag={info.categoryZh}
            name={info.name}
            img={info.img}
            kills={w.kills}
            topKills={top}
            mini={[
              { label: "KPM", value: fmtFixed(w.kpm) },
              { label: "命中", value: fmtPct(w.accuracy) },
              { label: "爆头", value: fmtPct(w.headshot_rate) },
            ]}
            foot={[`${fmtHours(w.time_seconds)} 小时`, adsShare(w)]}
          />
        ))}
      </Grid>
    </div>
  );
}

function adsShare(w: Bf6WeaponStats): string {
  const total = (w.ads_kills ?? 0) + (w.hipfire_kills ?? 0);
  return total ? `开镜击杀 ${fmtPct((w.ads_kills ?? 0) / total, 0)}` : "";
}

/* ------------------------------ 载具 ------------------------------ */

type VehicleFilter = "all" | VehicleGroup;
const VEHICLE_GROUP_LABEL: Record<VehicleGroup, string> = {
  air: "空中",
  ground: "地面",
  naval: "水面",
};

export function VehiclesTab({ stats }: { stats: Bf6PlayerStats }) {
  const [filter, setFilter] = useState<VehicleFilter>("all");
  const vehicles: Bf6VehicleStats[] = stats.vehicles;
  if (vehicles.length === 0) return <Empty text="还没有载具记录" />;

  const rowsAll = vehicles.map((v, i) => ({ v, rank: i + 1, info: vehicleInfo(v.id) }));
  const groups = (["air", "ground", "naval"] as const).filter((g) =>
    rowsAll.some((r) => r.info.group === g),
  );
  const options = [
    { key: "all" as const, label: "全部", count: vehicles.length },
    ...groups.map((g) => ({
      key: g,
      label: VEHICLE_GROUP_LABEL[g],
      count: rowsAll.filter((r) => r.info.group === g).length,
    })),
  ];
  const top = topKills(vehicles);
  const rows = rowsAll.filter(({ info }) => filter === "all" || info.group === filter);

  return (
    <div>
      <FilterChips options={options} value={filter} onChange={setFilter} />
      <Grid>
        {rows.map(({ v, rank, info }) => {
          const dmg = fmtCompact(v.damage);
          return (
            <GearCard
              key={v.id}
              rank={rank}
              tag={info.typeZh ?? VEHICLE_GROUP_LABEL[info.group]}
              name={info.name}
              img={info.img}
              fadeRight
              kills={v.kills}
              topKills={top}
              mini={[
                { label: "KPM", value: fmtFixed(v.kpm) },
                { label: "时长", value: `${fmtHours(v.time_seconds)}h` },
                { label: "出动", value: fmtInt(v.spawns) },
              ]}
              foot={[`伤害 ${dmg.value}${dmg.unit}`, `${fmtKm(v.distance_m)} km`]}
            />
          );
        })}
      </Grid>
    </div>
  );
}

/* ------------------------------ 配备 ------------------------------ */

type GadgetFilter = "all" | GadgetGroup;

function gadgetDetail(g: Bf6GadgetStats): string {
  if (g.repairs) return `修理 ${fmtInt(g.repairs)}`;
  if (g.vehicles_destroyed) return `摧毁载具 ${fmtInt(g.vehicles_destroyed)}`;
  if (g.damage) return `伤害 ${fmtInt(g.damage)}`;
  return "";
}

export function GadgetsTab({ stats }: { stats: Bf6PlayerStats }) {
  const [filter, setFilter] = useState<GadgetFilter>("all");
  const gadgets = stats.gadgets;
  if (gadgets.length === 0) return <Empty text="还没有配备记录" />;

  const rowsAll = gadgets.map((g, i) => ({ g, rank: i + 1, info: gadgetInfo(g.id) }));
  const groups = (Object.keys(GADGET_GROUPS) as GadgetGroup[]).filter((k) =>
    rowsAll.some((r) => r.info.group === k),
  );
  const options = [
    { key: "all" as const, label: "全部", count: gadgets.length },
    ...groups.map((k) => ({
      key: k,
      label: GADGET_GROUPS[k],
      count: rowsAll.filter((r) => r.info.group === k).length,
    })),
  ];
  const top = topKills(gadgets);
  const rows = rowsAll.filter(({ info }) => filter === "all" || info.group === filter);

  return (
    <div>
      <FilterChips options={options} value={filter} onChange={setFilter} />
      <Grid>
        {rows.map(({ g, rank, info }) => (
          <GearCard
            key={g.id}
            rank={rank}
            tag={GADGET_GROUPS[info.group]}
            name={info.name}
            img={info.img}
            kills={g.kills}
            topKills={top}
            foot={[`使用 ${fmtInt(g.uses)} 次`, gadgetDetail(g)]}
          />
        ))}
      </Grid>
    </div>
  );
}
