"use client";

import Link from "next/link";
import { ArrowDown, ArrowUp, Star, TrendingDown, TrendingUp } from "lucide-react";
import type { RoundPlayer, RoundRibbon, RoundScoreParts } from "@/lib/api/bf1";
import { classLabel } from "@/components/bf1/player-detail/format";
import { RIBBONS, ribbonImage } from "@/lib/bf1/codex/collection";
import { cn } from "@/lib/utils";

const RIBBON_BY_CODE = new Map(RIBBONS.map((r) => [r.code, r]));

/** 计分板上的分数：游戏计分板口径（不含勋带勋章奖励和结算奖励）；较早的对局没有分项，用总分 */
export function boardScore(p: RoundPlayer): number {
  return p.battle_score ?? p.score;
}

/** 名字旁的 MVP / 王牌小队标记 */
export function HonorBadges({ player: p, className }: { player: RoundPlayer; className?: string }) {
  if (!p.mvp && !p.ace_squad) return null;
  return (
    <span className={cn("flex shrink-0 items-center gap-1", className)}>
      {p.mvp ? (
        <span
          title="本局 MVP（游戏评选）"
          className="rounded-sm bg-amber-400 px-1 text-[9.5px] leading-[1.6] font-extrabold tracking-wide text-black"
        >
          MVP
        </span>
      ) : null}
      {p.ace_squad ? (
        <span
          title="本局王牌小队（游戏评选）"
          className="rounded-sm border border-amber-400/60 px-1 text-[9.5px] leading-[1.45] font-bold text-amber-300"
        >
          王牌
        </span>
      ) : null}
    </span>
  );
}

/**
 * 勋带图：原图 256 见方，勋带只占中间一条（x 17–239，y 约 90–167），按高度等比裁出这一条。
 * 与图鉴勋带页的裁法一致。
 */
export function RibbonStrip({ code, height = 20 }: { code: string; height?: number }) {
  const k = height / 42; // 图鉴页 42px 高时整图放到 141px
  const r = RIBBON_BY_CODE.get(code);
  return (
    <span
      className="relative block shrink-0 overflow-hidden"
      style={{ height, width: Math.round(122 * k) }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
      <img
        src={ribbonImage(code)}
        alt={r?.name ?? code}
        loading="lazy"
        className="absolute max-w-none"
        style={{ top: -49 * k, left: -9 * k, width: 141 * k, height: 141 * k }}
      />
    </span>
  );
}

/** 本局拿到的勋带：图 + 次数，悬停看名字和条件，点开进图鉴 */
export function RibbonList({ ribbons, game }: { ribbons: RoundRibbon[]; game: string }) {
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1.5">
      {ribbons.map((x) => {
        const r = RIBBON_BY_CODE.get(x.code);
        return (
          <li key={x.code}>
            <Link
              href={`/${game}/codex/ribbons#${x.code}`}
              title={r ? `${r.name}：${r.description}` : x.code}
              className="inline-action flex items-center gap-1 text-[11px] text-white/60 tabular-nums hover:text-amber-300"
            >
              <RibbonStrip code={x.code} />
              {x.count > 1 ? <span>×{x.count}</span> : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

const RECORD_LABEL: Record<string, (v: number) => string> = {
  max_killstreak: (v) => `最高连杀新纪录 ${v}`,
  longest_headshot: (v) => `最远爆头新纪录 ${v} 米`,
  max_nemesis_streak: (v) => `最高宿敌连杀新纪录 ${v}`,
};

/** 这一局的成长与纪录：升级、兵种升级、技巧值、新纪录、勋章、服役星 */
export function GrowthChips({ player: p }: { player: RoundPlayer }) {
  const chips: { key: string; text: string; tone?: "gold" | "dim"; title?: string }[] = [];
  if (p.rank_to) chips.push({ key: "rank", text: `升到 ${p.rank_to} 级`, tone: "gold" });
  for (const kit of p.kit_ranks ?? [])
    chips.push({ key: `kit-${kit}`, text: `${classLabel(kit)}升级`, tone: "gold" });
  for (const [k, v] of Object.entries(p.records ?? {}))
    chips.push({ key: k, text: RECORD_LABEL[k]?.(v) ?? `${k} ${v}`, tone: "gold" });
  if (p.medals) chips.push({ key: "medals", text: `完成勋章 ${p.medals}`, tone: "gold" });
  for (const s of p.stars ?? [])
    chips.push({
      key: `star-${s.name}`,
      text: `${s.name ?? "未知"} ★${s.stars}`,
      title: `${s.name ?? "未知"}击杀满 ${s.stars * 100}，获得第 ${s.stars} 颗服役星`,
    });
  if (p.skill_delta)
    chips.push({
      key: "skill",
      text: `技巧值 ${p.skill_delta > 0 ? "+" : ""}${p.skill_delta.toFixed(1)}`,
      tone: "dim",
    });
  if (!chips.length) return null;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <li
          key={c.key}
          title={c.title}
          className={cn(
            "flex items-center gap-1 rounded-sm px-1.5 py-px text-[11px] whitespace-nowrap",
            c.tone === "gold"
              ? "bg-amber-400/12 text-amber-200"
              : c.tone === "dim"
                ? "bg-white/[0.06] text-white/55"
                : "bg-white/[0.08] text-white/80",
          )}
        >
          {c.key.startsWith("star-") ? (
            <Star className="size-3 fill-amber-300 text-amber-300" />
          ) : null}
          {c.text}
        </li>
      ))}
    </ul>
  );
}

const BOARD_PARTS: { key: keyof RoundScoreParts; label: string; color: string }[] = [
  { key: "general", label: "战斗", color: "bg-sky-400/80" },
  { key: "team", label: "团队", color: "bg-emerald-400/80" },
  { key: "squad", label: "小队", color: "bg-violet-400/80" },
  { key: "objective", label: "目标", color: "bg-amber-400/85" },
  { key: "other", label: "其他", color: "bg-white/35" },
];
const XP_PARTS: { key: keyof RoundScoreParts; label: string; color: string }[] = [
  { key: "award", label: "勋带勋章", color: "bg-amber-200/40" },
  { key: "bonus", label: "结算奖励", color: "bg-white/15" },
];

/**
 * 得分构成：一根条，左边是计分板上的分数（战斗、团队、小队、目标、其他），右边淡色是结算时另给的
 * 经验（勋带勋章奖励、结算奖励）。「其他」是总分减去各项的零头，主要是载具和巨兽，可能为负，为负不画。
 */
export function ScoreBreakdown({ parts, total }: { parts: RoundScoreParts; total: number }) {
  const all = [...BOARD_PARTS, ...XP_PARTS].filter((x) => parts[x.key] > 0);
  const sum = all.reduce((s, x) => s + parts[x.key], 0) || 1;
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-white/[0.06]">
        {all.map((x) => (
          <span
            key={x.key}
            className={x.color}
            style={{ width: `${(parts[x.key] / sum) * 100}%` }}
          />
        ))}
      </div>
      <dl className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] tabular-nums">
        {all.map((x) => (
          <div key={x.key} className="flex items-center gap-1">
            <span className={cn("size-1.5 rounded-full", x.color)} />
            <dt className="text-white/45">{x.label}</dt>
            <dd className="text-white/80">{parts[x.key].toLocaleString("en-US")}</dd>
          </div>
        ))}
        <div className="flex items-center gap-1">
          <dt className="text-white/45">总经验</dt>
          <dd className="text-white/80">{total.toLocaleString("en-US")}</dd>
        </div>
      </dl>
    </div>
  );
}

/** 在场不足这么久不和生涯比：几分钟的数字起伏太大 */
const MIN_COMPARE_SECONDS = 300;
/** 命中率、爆头率的最小样本：开火发数、步兵击杀数（载具击杀没有爆头） */
const MIN_COMPARE_SHOTS = 50;
const MIN_COMPARE_KILLS = 5;

export type Compare = {
  label: string;
  value: number;
  career: number;
  /** 加上这一局之后的生涯值 */
  after: number | null;
  fmt: (v: number) => string;
};

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/**
 * 和这名玩家这一局之前的生涯水平对比的几项：KD、KPM、SPM、命中率、爆头率（爆头 ÷ 击杀）。
 * 只在单局详情里有；在场太短、没有快照，或旧快照没有的项不列。
 */
export function careerCompare(p: RoundPlayer): Compare[] {
  const c = p.career;
  const a = p.career_after;
  if (!c || p.seconds < MIN_COMPARE_SECONDS) return [];
  const shots = p.combat?.shots ?? 0;
  const infantryKills = p.kills - p.vehicle_kills;
  const items = [
    { label: "K/D", value: p.kd, career: c.kd, after: a?.kd, fmt: (v: number) => v.toFixed(2) },
    { label: "KPM", value: p.kpm, career: c.kpm, after: a?.kpm, fmt: (v: number) => v.toFixed(2) },
    {
      label: "SPM",
      value: p.spm,
      career: c.spm,
      after: a?.spm,
      fmt: (v: number) => Math.round(v).toString(),
    },
    {
      label: "命中率",
      value: shots >= MIN_COMPARE_SHOTS ? (p.combat?.hits ?? 0) / shots : null,
      career: c.accuracy,
      after: a?.accuracy,
      fmt: pct,
    },
    {
      label: "爆头率",
      value:
        infantryKills >= MIN_COMPARE_KILLS && p.combat
          ? (p.combat.headshots ?? 0) / p.kills // 和生涯同口径：爆头 ÷ 全部击杀
          : null,
      career: c.headshot_rate,
      after: a?.headshot_rate,
      fmt: pct,
    },
  ];
  return items
    .filter((x) => x.value != null && x.career != null)
    .map((x) => ({ ...x, after: x.after ?? null }) as Compare);
}

export function CareerCompare({ items }: { items: Compare[] }) {
  return (
    <dl className="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-x-3 gap-y-2 tabular-nums">
      {items.map((x) => (
        <div key={x.label}>
          <dt className="text-[10.5px] text-white/40">{x.label}</dt>
          <dd className="text-[14px] leading-tight font-semibold text-white">{x.fmt(x.value)}</dd>
          <dd className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[10.5px] text-white/40">
            生涯 {x.fmt(x.career)}
            {x.after != null ? <CareerShift before={x.career} after={x.after} /> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** 这一局让生涯值变了多少（相对变化），和首页「较 24 小时前」一个样式 */
function CareerShift({ before, after }: { before: number; after: number }) {
  if (before <= 0) return null;
  const change = (after / before - 1) * 100;
  if (Math.abs(change) < 0.005) return <span className="text-white/35">持平</span>;
  const up = change > 0;
  const Icon = up ? TrendingUp : TrendingDown;
  const size = Math.abs(change) < 0.01 ? "<0.01" : Math.abs(change).toFixed(2);
  return (
    <span
      title="这一局让生涯值变化的幅度"
      className={cn(
        "flex items-center gap-0.5 font-semibold",
        up ? "text-emerald-400" : "text-rose-400",
      )}
    >
      <Icon className="size-3" />
      {up ? "+" : "−"}
      {size}%
    </span>
  );
}

/** 高于生涯绿色向上、低于红色向下；差不到 5% 视为持平，不标 */
export function Trend({ now, career }: { now: number; career: number }) {
  if (career <= 0 || Math.abs(now - career) / career < 0.05) return null;
  const up = now > career;
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <Icon
      aria-label={up ? "高于生涯" : "低于生涯"}
      className={cn("size-3", up ? "text-emerald-400" : "text-rose-400")}
    />
  );
}

/** 这一局的目标、团队与战斗明细，按游戏内的说法；只列非零项。soldier_damage、vehicle_damage 数值很小、含义没核实，不列 */
export const OBJECTIVE_LABEL: Record<string, string> = {
  flag_captures: "占点",
  flag_defends: "守点",
  bombs_placed: "安放炸弹",
  bombs_defused: "拆除炸弹",
  artillery_defense_kills: "火炮防守击杀",
  pigeons_delivered: "送出信鸽",
  pigeons_written: "写信",
  pigeon_carriers_killed: "击杀信鸽兵",
  resupplies: "补给",
  spot_assists: "索敌助攻",
  suppression_assists: "压制助攻",
  squad_spawns: "小队重生",
  orders_completed: "完成命令",
  squad_kill_assists: "小队击杀助攻",
};

export const COMBAT_LABEL: Record<string, string> = {
  headshots: "爆头",
  avenger_kills: "复仇击杀",
  savior_kills: "救星击杀",
  nemesis_kills: "宿敌击杀",
  squad_wipes: "团灭",
  vehicles_destroyed: "摧毁载具",
};
