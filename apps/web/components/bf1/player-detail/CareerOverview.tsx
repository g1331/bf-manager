"use client";

import { motion } from "framer-motion";
import {
  ArrowRight,
  Flame,
  Handshake,
  HeartPulse,
  Skull,
  Syringe,
  Tag,
  Target,
  Wrench,
  Crosshair,
  type LucideIcon,
} from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { Skeleton } from "@/components/ui/skeleton";
import type { PlayerStatsSummary, SoldierClassStat, VehicleStat, WeaponStat } from "@/lib/api/bf1";
import { rarityHex } from "@/lib/bf1/rarity";
import { cn, formatDuration } from "@/lib/utils";
import { classLabel, fmtFixed, fmtFull, fmtPct, perMinute, winRate } from "./format";

/** 概览分区：战斗 + 团队贡献，兵种 + 常用装备，两行左宽右窄 */
export function CareerOverview({
  summary,
  soldiers,
  weapons,
  vehicles,
  onShowAll,
}: {
  summary: PlayerStatsSummary;
  soldiers: SoldierClassStat[];
  weapons: WeaponStat[] | undefined;
  vehicles: VehicleStat[] | undefined;
  onShowAll: (tab: "weapons" | "vehicles") => void;
}) {
  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <CombatPanel s={summary} />
        <TeamworkPanel s={summary} />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <ClassPanel soldiers={soldiers} best={summary.best_class} />
        <TopGearPanel weapons={weapons} vehicles={vehicles} onShowAll={onShowAll} />
      </div>
    </div>
  );
}

export function Panel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className={cn("bg-black/45 p-4 backdrop-blur-sm sm:p-6", className)}
    >
      {children}
    </Bf1Panel>
  );
}

/* ----------------------------- 战斗 ----------------------------- */

function CombatPanel({ s }: { s: PlayerStatsSummary }) {
  const rate = winRate(s.wins, s.losses);
  const tiles: ReadonlyArray<[string, string, LucideIcon, boolean?]> = [
    ["击杀", fmtFull(s.kills), Crosshair],
    ["死亡", fmtFull(s.deaths), Skull],
    ["协助击杀", fmtFull(s.assists), Handshake],
    ["最高连杀", fmtFull(s.max_killstreak), Flame, true],
    [
      "最远爆头",
      s.longest_headshot_meters != null ? `${fmtFull(s.longest_headshot_meters)} m` : "—",
      Target,
    ],
    ["狗牌", fmtFull(s.dogtags), Tag],
  ];
  return (
    <Panel>
      <SectionHeading className="mb-5">战斗</SectionHeading>
      <div className="grid gap-5 sm:grid-cols-2">
        <SplitBar
          title="击杀构成"
          left={{ label: "步战", value: s.infantry_kills, color: "#f59e0b" }}
          right={{ label: "载具", value: s.vehicle_kills, color: "#64748b" }}
        />
        <SplitBar
          title={`胜负 · 胜率 ${fmtPct(rate)}`}
          left={{ label: "胜", value: s.wins, color: "#10b981" }}
          right={{ label: "负", value: s.losses, color: "#ef4444" }}
        />
      </div>
      <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-white/10 pt-5 sm:grid-cols-3">
        {tiles.map(([label, value, Icon, accent]) => (
          <div key={label}>
            <div className="flex items-center gap-1.5 text-[11px] tracking-wider text-white/50">
              <Icon className="size-3.5 text-white/40" />
              {label}
            </div>
            <div
              className={cn(
                "font-display mt-1 text-2xl font-bold tabular-nums",
                accent ? "text-amber-300" : "text-white",
              )}
            >
              {value}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

/** 二分占比条：上方标题，条两端分别标数量与百分比 */
function SplitBar({
  title,
  left,
  right,
}: {
  title: string;
  left: { label: string; value: number | null; color: string };
  right: { label: string; value: number | null; color: string };
}) {
  const a = left.value ?? 0;
  const b = right.value ?? 0;
  const total = a + b;
  const pct = total > 0 ? (a / total) * 100 : 50;
  return (
    <div>
      <div className="text-[11px] tracking-wider text-white/50">{title}</div>
      <div className="mt-2 flex h-2.5 gap-[3px]">
        <motion.div
          className="h-full"
          style={{ background: left.color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.9, ease: "easeOut" }}
        />
        <div className="h-full flex-1" style={{ background: right.color, opacity: 0.75 }} />
      </div>
      <div className="mt-1.5 flex justify-between text-xs tabular-nums">
        <span className="text-white/80">
          {left.label} {fmtFull(left.value)}
          <span className="ml-1 text-white/40">{total > 0 ? `${pct.toFixed(0)}%` : ""}</span>
        </span>
        <span className="text-white/80">
          <span className="mr-1 text-white/40">
            {total > 0 ? `${(100 - pct).toFixed(0)}%` : ""}
          </span>
          {right.label} {fmtFull(right.value)}
        </span>
      </div>
    </div>
  );
}

/* ----------------------------- 团队贡献 ----------------------------- */

function TeamworkPanel({ s }: { s: PlayerStatsSummary }) {
  const hours = (s.time_played_seconds ?? 0) / 3600;
  const items: ReadonlyArray<[string, number | null, LucideIcon]> = [
    ["复活", s.revives, HeartPulse],
    ["治疗", s.heals, Syringe],
    ["修理", s.repairs, Wrench],
  ];
  return (
    <Panel className="flex h-full flex-col">
      <SectionHeading className="mb-5">团队贡献</SectionHeading>
      <div className="flex flex-1 flex-col justify-around gap-4">
        {items.map(([label, value, Icon]) => (
          <div key={label} className="flex items-center gap-4">
            <span className="flex size-10 shrink-0 items-center justify-center border border-white/15 bg-white/[0.04]">
              <Icon className="size-5 text-white/70" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] tracking-wider text-white/50">{label}</div>
              <div className="font-display text-2xl font-bold text-white tabular-nums">
                {fmtFull(value)}
              </div>
            </div>
            <div className="text-right text-xs text-white/45 tabular-nums">
              {value != null && hours > 0 ? `${(value / hours).toFixed(1)} / 小时` : ""}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

/* ----------------------------- 兵种 ----------------------------- */

function ClassPanel({ soldiers, best }: { soldiers: SoldierClassStat[]; best: string | null }) {
  const rows = [...soldiers].sort((a, b) => b.time_seconds - a.time_seconds);
  const totalTime = rows.reduce((sum, r) => sum + r.time_seconds, 0) || 1;
  const topTime = Math.max(rows[0]?.time_seconds ?? 0, 1);
  return (
    <Panel>
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <SectionHeading className="mb-0">兵种</SectionHeading>
        <span className="text-[11px] text-white/40">按游玩时长排序</span>
      </div>
      {rows.length === 0 ? (
        <div className="py-8 text-center text-sm text-white/40">暂无兵种数据</div>
      ) : (
        <>
          <div className="hidden grid-cols-[3rem_minmax(0,1fr)_5rem_5rem_4rem_4rem] gap-x-4 px-1 pb-2 text-[11px] tracking-wider text-white/40 sm:grid">
            <span />
            <span>兵种 · 时长占比</span>
            <span className="text-right">时长</span>
            <span className="text-right">击杀</span>
            <span className="text-right">KPM</span>
            <span className="text-right">SPM</span>
          </div>
          <ol className="space-y-1.5">
            {rows.map((r, i) => {
              const isBest = r.class === best;
              const share = r.time_seconds / totalTime;
              return (
                <li
                  key={r.class}
                  className={cn(
                    "grid grid-cols-[3rem_minmax(0,1fr)] items-center gap-x-4 gap-y-1 px-1 py-1.5 sm:grid-cols-[3rem_minmax(0,1fr)_5rem_5rem_4rem_4rem]",
                    isBest && "bg-amber-500/[0.07]",
                  )}
                >
                  <div className="row-span-2 h-12 w-12 overflow-hidden border border-white/10 bg-white/[0.04] sm:row-span-1">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`/bf1/soldiers/portraits/${r.class}.png`}
                      alt=""
                      loading="lazy"
                      className="h-[180%] w-full object-cover object-top"
                    />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-baseline gap-2 text-sm">
                      <span
                        className={cn("font-semibold", isBest ? "text-amber-300" : "text-white")}
                      >
                        {classLabel(r.class)}
                      </span>
                      {isBest ? (
                        <span className="bg-amber-400 px-1 text-[10px] leading-4 font-bold text-black">
                          最佳
                        </span>
                      ) : null}
                      <span className="ml-auto text-xs text-white/50 tabular-nums">
                        {fmtPct(share, 0)}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1 bg-white/[0.07]">
                      <motion.div
                        className="h-full"
                        style={{ background: isBest ? rarityHex.gold : "rgba(255,255,255,0.45)" }}
                        initial={{ width: 0 }}
                        animate={{ width: `${(r.time_seconds / topTime) * 100}%` }}
                        transition={{ duration: 0.9, delay: i * 0.05, ease: "easeOut" }}
                      />
                    </div>
                  </div>
                  {/* 窄屏把四个数字折到第二行 */}
                  <div className="col-start-2 flex flex-wrap gap-x-3 text-xs whitespace-nowrap text-white/55 tabular-nums sm:contents sm:text-sm sm:text-white/85">
                    <span className="sm:text-right">{formatDuration(r.time_seconds)}</span>
                    <span className="sm:text-right">
                      <span className="sm:hidden">击杀 </span>
                      {fmtFull(r.kills)}
                    </span>
                    <span className="sm:text-right">
                      <span className="sm:hidden">KPM </span>
                      {fmtFixed(perMinute(r.kills, r.time_seconds))}
                    </span>
                    <span className="sm:text-right">
                      <span className="sm:hidden">SPM </span>
                      {fmtFull(perMinute(r.score, r.time_seconds))}
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </Panel>
  );
}

/* ----------------------------- 常用装备 ----------------------------- */

function TopGearPanel({
  weapons,
  vehicles,
  onShowAll,
}: {
  weapons: WeaponStat[] | undefined;
  vehicles: VehicleStat[] | undefined;
  onShowAll: (tab: "weapons" | "vehicles") => void;
}) {
  return (
    <Panel className="flex h-full flex-col">
      <GearList title="常用武器" items={weapons} limit={5} onShowAll={() => onShowAll("weapons")} />
      <div className="my-5 border-t border-white/10" />
      <GearList
        title="常用载具"
        items={vehicles}
        limit={3}
        onShowAll={() => onShowAll("vehicles")}
      />
    </Panel>
  );
}

function GearList({
  title,
  items,
  limit,
  onShowAll,
}: {
  title: string;
  items: (WeaponStat | VehicleStat)[] | undefined;
  limit: number;
  onShowAll: () => void;
}) {
  const top = (items ?? [])
    .filter((it) => (it.kills ?? 0) > 0)
    .sort((a, b) => (b.kills ?? 0) - (a.kills ?? 0))
    .slice(0, limit);
  const max = Math.max(top[0]?.kills ?? 0, 1);
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <SectionHeading className="mb-0">{title}</SectionHeading>
        <button
          type="button"
          onClick={onShowAll}
          className="flex items-center gap-1 text-xs text-white/50 transition-colors hover:text-white"
        >
          全部
          <ArrowRight className="size-3.5" />
        </button>
      </div>
      {items == null ? (
        <div className="space-y-2">
          {Array.from({ length: limit }, (_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      ) : top.length === 0 ? (
        <div className="py-4 text-center text-xs text-white/40">暂无记录</div>
      ) : (
        <ol className="space-y-2.5">
          {top.map((it, i) => (
            <li key={`${it.name}-${i}`} className="flex items-center gap-3">
              <div className="flex h-10 w-20 shrink-0 items-center justify-center bg-white/[0.04]">
                {(it.skin_image ?? it.image) ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={(it.skin_image ?? it.image)!}
                    alt=""
                    loading="lazy"
                    className="max-h-full max-w-full object-contain p-0.5"
                  />
                ) : null}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="truncate text-sm text-white" title={it.name ?? ""}>
                    {it.name}
                  </span>
                  <span className="ml-auto shrink-0 text-xs text-white/80 tabular-nums">
                    {fmtFull(it.kills)}
                  </span>
                </div>
                <div className="mt-1.5 h-1 bg-white/[0.07]">
                  <motion.div
                    className="h-full bg-amber-400/80"
                    initial={{ width: 0 }}
                    animate={{ width: `${((it.kills ?? 0) / max) * 100}%` }}
                    transition={{ duration: 0.9, delay: i * 0.05, ease: "easeOut" }}
                  />
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
