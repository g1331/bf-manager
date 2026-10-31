"use client";

import { Fragment, useState } from "react";
import type { RoundPlayer, RoundWeapon } from "@/lib/api/bf1";
import {
  COMBAT_LABEL,
  CareerCompare,
  GrowthChips,
  OBJECTIVE_LABEL,
  RibbonList,
  ScoreBreakdown,
  Trend,
  careerCompare,
} from "@/components/bf1/rounds/RoundHonors";
import { cn } from "@/lib/utils";

/** 一局里的时长：不到一分钟写秒，其余写分钟 */
function fmtRoundSeconds(s: number): string {
  if (!s) return "—";
  return s < 60 ? `${s} 秒` : `${Math.round(s / 60)} 分钟`;
}

/**
 * 这一局用得最多的武器载具：击杀最多，没有击杀时取用得最久的（列表已按这个顺序排好）。
 * 战马的击杀其实是骑在马上用的武器打的，有别的武器拿到击杀时让给它。
 */
export function mainWeapon(p: RoundPlayer): RoundWeapon | null {
  const used = p.weapons?.filter((w) => w.kills > 0 || w.seconds > 0) ?? [];
  return used.find((w) => w.kills > 0 && !w.shared_kills) ?? used[0] ?? null;
}

export function WeaponImage({ weapon, className }: { weapon: RoundWeapon; className?: string }) {
  if (!weapon.image) return <span className={cn("block shrink-0", className)} />;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={weapon.image}
      alt={weapon.name ?? ""}
      loading="lazy"
      className={cn("shrink-0 object-contain", className)}
    />
  );
}

/** 先列这么多件，其余点开 */
const FIRST = 6;

/** 展开明细里的一块，带小标题 */
function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-1.5 text-[10.5px] font-medium tracking-wide text-white/40">{title}</h4>
      {children}
    </section>
  );
}

/**
 * 计分板里展开的一个人：这一局的荣誉与成长、其他数据、和生涯的对比、得分构成、勋带，
 * 以及用过的武器载具（击杀多的在前）。都是生涯差值；荣誉、得分构成、勋带和目标战斗明细
 * 2026-10-31 起才有，武器载具更早，功能上线前的局或当时没读到的人没有对应部分。
 */
export function RoundPlayerBreakdown({ player: p, game }: { player: RoundPlayer; game: string }) {
  const [all, setAll] = useState(false);
  const used = (p.weapons ?? []).filter((w) => w.kills > 0 || w.seconds > 0 || w.destroyed > 0);
  const shown = all ? used : used.slice(0, FIRST);
  const compare = careerCompare(p);
  const compared = new Set(compare.map((x) => x.label));
  const shots = p.combat?.shots ?? 0;
  const facts: [string, string | number][] = [
    ["在场", fmtRoundSeconds(p.seconds)],
    ["助攻", p.assists],
    ["复活", p.revives],
    ["治疗", p.heals],
    ["修理", p.repairs],
    ["狗牌", p.dogtags],
    ["载具击杀", p.vehicle_kills],
    ...Object.entries(p.objective ?? {}).map(
      ([k, v]) => [OBJECTIVE_LABEL[k] ?? k, v] as [string, number],
    ),
    ...Object.entries(p.combat ?? {})
      .filter(([k]) => k in COMBAT_LABEL)
      .map(([k, v]) => [COMBAT_LABEL[k], v.toLocaleString("en-US")] as [string, string]),
  ];
  // 上面和生涯对比过的几项不再重复列
  if (!compared.has("命中率") && shots > 0)
    facts.push(["命中率", `${Math.round(((p.combat?.hits ?? 0) / shots) * 100)}%`]);
  if (!compared.has("KPM")) facts.push(["KPM", p.kpm != null ? p.kpm.toFixed(2) : "—"]);
  if (!compared.has("SPM")) facts.push(["SPM", p.spm ?? "—"]);
  return (
    <div className="@container space-y-4 py-3 pr-1 pl-2">
      <GrowthChips player={p} />
      <dl className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] tabular-nums">
        {facts.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-1">
            <dt className="text-white/40">{label}</dt>
            <dd className="font-medium text-white/80">{value}</dd>
          </div>
        ))}
      </dl>
      {compare.length ? (
        <Block title="对比生涯">
          <CareerCompare items={compare} />
        </Block>
      ) : null}
      {p.score_parts ? (
        <Block title="得分构成">
          <ScoreBreakdown parts={p.score_parts} total={p.score} />
        </Block>
      ) : null}
      {p.ribbons?.length ? (
        <Block title="勋带">
          <RibbonList ribbons={p.ribbons} game={game} />
        </Block>
      ) : null}
      {p.weapons == null ? (
        <p className="text-[11.5px] text-white/35">这一局没有武器载具数据</p>
      ) : used.length === 0 ? (
        <p className="text-[11.5px] text-white/35">这一局没有用到武器载具</p>
      ) : (
        <div>
          <div className={cn(COLS, "border-b border-white/10 pb-1 text-[10.5px] text-white/40")}>
            <span className="hidden @[17rem]:block" />
            <span>武器载具</span>
            <span className="text-right">击杀</span>
            <span className="text-right">时长</span>
          </div>
          <ul>
            {shown.map((w, i) => (
              <WeaponRow key={`${w.kind}-${w.name}-${i}`} weapon={w} />
            ))}
          </ul>
          {used.length > FIRST ? (
            <button
              type="button"
              onClick={() => setAll(!all)}
              className="mt-1 text-[11px] text-white/45 hover:text-amber-300"
            >
              {all ? "收起" : `全部 ${used.length} 件`}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** 图片、名称、击杀、时长四列；很窄时去掉图片 */
const COLS =
  "grid grid-cols-[minmax(0,1fr)_2.5rem_3.5rem] items-center gap-x-2 @[17rem]:grid-cols-[3.5rem_minmax(0,1fr)_2.5rem_3.5rem]";

/** 单件武器开火不到这么多发不和生涯命中率比，样本太小 */
const MIN_COMPARE_SHOTS = 50;

function WeaponRow({ weapon: w }: { weapon: RoundWeapon }) {
  // 名称下面一行小字：分类，武器加爆头和命中率，载具加摧毁。霰弹枪一发多弹丸，命中率可以超过 100%。
  // 命中率开火够多时标出比生涯高还是低，悬停看生涯值。
  // 战马的击杀和骑马时用的武器重复，分类换成这句说明，窄屏也要完整显示
  const note = w.shared_kills && w.kills > 0;
  const accuracy = w.kind === "weapon" && w.shots > 0 ? w.hits / w.shots : null;
  const career =
    accuracy != null && w.shots >= MIN_COMPARE_SHOTS && w.career_accuracy
      ? w.career_accuracy
      : null;
  const parts: { key: string; node: React.ReactNode; text: string }[] = [];
  const add = (key: string, text: string | null | undefined, node?: React.ReactNode) => {
    if (text) parts.push({ key, text, node: node ?? text });
  };
  add("category", note ? "击杀含骑马时用武器打的" : w.category);
  if (w.kind === "weapon" && w.headshots) add("headshots", `爆头 ${w.headshots}`);
  if (accuracy != null) {
    const text = `命中率 ${Math.round(accuracy * 100)}%`;
    add(
      "accuracy",
      career != null ? `${text}（生涯 ${Math.round(career * 100)}%）` : text,
      career != null ? (
        <span className="inline-flex items-center gap-0.5 align-bottom">
          {text}
          <Trend now={accuracy} career={career} />
        </span>
      ) : (
        text
      ),
    );
  }
  if (w.kind === "vehicle" && w.destroyed) add("destroyed", `摧毁 ${w.destroyed}`);
  const title = parts.map((x) => x.text).join(" · ");
  return (
    <li
      className={cn(
        COLS,
        "border-b border-white/[0.05] py-1 text-[12px] tabular-nums last:border-0",
      )}
    >
      <WeaponImage weapon={w} className="hidden h-6 w-14 @[17rem]:block" />
      <div className="min-w-0">
        <div className="truncate text-white/85">{w.name ?? "未知"}</div>
        {parts.length ? (
          <div
            className={cn("text-[10px] leading-tight text-white/40", !note && "truncate")}
            title={title}
          >
            {parts.map((x, i) => (
              <Fragment key={x.key}>
                {i ? " · " : null}
                {x.node}
              </Fragment>
            ))}
          </div>
        ) : null}
      </div>
      <span className={cn("text-right", w.kills ? "font-semibold text-white" : "text-white/35")}>
        {w.kills}
      </span>
      <span className="text-right text-white/60">{fmtRoundSeconds(w.seconds)}</span>
    </li>
  );
}
