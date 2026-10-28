"use client";

import { useState } from "react";
import type { RoundPlayer, RoundWeapon } from "@/lib/api/bf1";
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

/**
 * 计分板里展开的一个人：这一局的其他数据，以及用过的武器载具（击杀多的在前）。
 * 武器载具同样是生涯差值；功能上线前的局，或当时没读到的人没有这部分。
 */
export function RoundPlayerBreakdown({ player: p }: { player: RoundPlayer }) {
  const [all, setAll] = useState(false);
  const used = (p.weapons ?? []).filter((w) => w.kills > 0 || w.seconds > 0 || w.destroyed > 0);
  const shown = all ? used : used.slice(0, FIRST);
  const facts: [string, string | number][] = [
    ["在场", fmtRoundSeconds(p.seconds)],
    ["助攻", p.assists],
    ["复活", p.revives],
    ["治疗", p.heals],
    ["修理", p.repairs],
    ["狗牌", p.dogtags],
    ["载具击杀", p.vehicle_kills],
    ["KPM", p.kpm != null ? p.kpm.toFixed(2) : "—"],
    ["SPM", p.spm ?? "—"],
  ];
  return (
    <div className="@container space-y-3 py-3 pr-1 pl-2">
      <dl className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] tabular-nums">
        {facts.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-1">
            <dt className="text-white/40">{label}</dt>
            <dd className="font-medium text-white/80">{value}</dd>
          </div>
        ))}
      </dl>
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

function WeaponRow({ weapon: w }: { weapon: RoundWeapon }) {
  // 名称下面一行小字：分类，武器加爆头和命中率，载具加摧毁。霰弹枪一发多弹丸，命中率可以超过 100%。
  // 战马的击杀和骑马时用的武器重复，分类换成这句说明，窄屏也要完整显示
  const note = w.shared_kills && w.kills > 0;
  const detail = [
    note ? "击杀含骑马时用武器打的" : w.category,
    w.kind === "weapon" && w.headshots ? `爆头 ${w.headshots}` : null,
    w.kind === "weapon" && w.shots > 0 ? `命中率 ${Math.round((w.hits / w.shots) * 100)}%` : null,
    w.kind === "vehicle" && w.destroyed ? `摧毁 ${w.destroyed}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
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
        {detail ? (
          <div
            className={cn("text-[10px] leading-tight text-white/40", !note && "truncate")}
            title={detail}
          >
            {detail}
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
