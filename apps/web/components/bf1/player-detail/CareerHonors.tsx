"use client";

import Link from "next/link";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { RibbonStrip } from "@/components/bf1/rounds/RoundHonors";
import type {
  CareerHonors,
  CareerMap,
  CareerMisc,
  CareerMode,
  CareerRibbon,
  EliteKitStat,
} from "@/lib/api/bf1";
import { mapImage } from "@/lib/bf1/codex/battlefield";
import { groupBy, RIBBONS } from "@/lib/bf1/codex/collection";
import { mapLabel } from "@/lib/bf1/catalog";
import { cn, formatDuration } from "@/lib/utils";
import { Panel } from "./CareerOverview";
import { fmtFixed, fmtFull, fmtHours, fmtPct, perMinute } from "./format";

const MODE_LABEL: Record<string, string> = {
  conquest: "征服",
  operations: "行动模式",
  rush: "突袭",
  frontlines: "前线",
  domination: "抢攻",
  war_pigeons: "战争信鸽",
  team_deathmatch: "团队死斗",
  air_assault: "空中突击",
};

const ELITE_LABEL: Record<string, string> = {
  sentry: "哨兵",
  flamethrower: "喷火兵",
  trench_raider: "战壕奇兵",
  tank_hunter: "坦克猎手",
  infiltrator: "入侵者",
};

const RIBBON_GROUPS = groupBy(RIBBONS, (r) => r.category);

/** 荣誉：MVP、王牌小队、勋带、勋章等几个数字，下面是勋带墙 */
export function HonorsPanel({
  honors,
  misc,
  ribbons,
  game,
}: {
  honors: CareerHonors;
  misc: CareerMisc | null | undefined;
  ribbons: CareerRibbon[] | null | undefined;
  game: string;
}) {
  const tiles: [string, string][] = [
    ["MVP", fmtFull(honors.mvp)],
    ["王牌小队", fmtFull(honors.ace_squad)],
    ["勋带", fmtFull(honors.ribbons)],
    ["勋章", fmtFull(honors.medals)],
  ];
  if (misc) {
    tiles.push(["完成率", fmtPct(misc.completion_rate)]);
    tiles.push(["观战", fmtHours(misc.spectator_seconds)]);
  }
  return (
    <Panel>
      <SectionHeading className="mb-5">荣誉</SectionHeading>
      <dl className="grid grid-cols-3 gap-x-6 gap-y-4 sm:grid-cols-6">
        {tiles.map(([label, value]) => (
          <div key={label}>
            <dt className="text-[11px] tracking-wider text-white/50">{label}</dt>
            <dd className="font-display mt-1 text-xl font-bold text-white tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {ribbons ? <RibbonWall ribbons={ribbons} game={game} /> : null}
    </Panel>
  );
}

/** 勋带墙：按图鉴分类排，各拿过几次，没拿过的置灰；点开进图鉴 */
function RibbonWall({ ribbons, game }: { ribbons: CareerRibbon[]; game: string }) {
  const counts = new Map(ribbons.map((r) => [r.code, r.count]));
  const got = ribbons.filter((r) => r.count > 0).length;
  return (
    <section className="mt-6 border-t border-white/10 pt-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-white">勋带</h3>
        <span className="text-[11px] text-white/40 tabular-nums">
          {got} / {ribbons.length}
        </span>
      </div>
      <div className="space-y-4">
        {RIBBON_GROUPS.map((g) => (
          <div key={g.key}>
            <div className="mb-1.5 text-[11px] text-white/45">{g.key}</div>
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] gap-x-3 gap-y-2">
              {g.items.map((r) => {
                const n = counts.get(r.code) ?? 0;
                return (
                  <li key={r.code}>
                    <Link
                      href={`/${game}/codex/ribbons#${r.code}`}
                      title={`${r.name}：${r.description}`}
                      className={cn(
                        "inline-action flex items-center gap-1.5 text-[11px] tabular-nums transition-opacity hover:opacity-100",
                        n ? "text-white/75" : "opacity-30 grayscale",
                      )}
                    >
                      <RibbonStrip code={r.code} />
                      <span>{n ? `×${fmtFull(n)}` : ""}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

/** 各模式胜负与目标得分（sc_<模式> 只含占点、炸弹、信鸽这类目标分，不含击杀和团队分），按局数倒序 */
export function ModesPanel({ modes }: { modes: CareerMode[] }) {
  const rows = [...modes].sort((a, b) => b.wins + b.losses - (a.wins + a.losses));
  return (
    <Panel>
      <SectionHeading className="mb-4">模式</SectionHeading>
      {rows.length === 0 ? (
        <div className="py-8 text-center text-sm text-white/40">暂无模式数据</div>
      ) : (
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="text-[11px] tracking-wider text-white/40">
              <th className="pb-2 text-left font-normal">模式</th>
              <th className="pb-2 text-right font-normal">胜 / 负</th>
              <th className="pb-2 text-right font-normal">胜率</th>
              <th className="pb-2 text-right font-normal">目标得分</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.mode} className="border-t border-white/[0.06]">
                <td className="py-2 text-white">{MODE_LABEL[m.mode] ?? m.mode}</td>
                <td className="py-2 text-right text-white/70">
                  {fmtFull(m.wins)} / {fmtFull(m.losses)}
                </td>
                <td className="py-2 pl-3 text-right text-white">{fmtPct(m.win_rate)}</td>
                <td className="py-2 pl-3 text-right text-white/70">{fmtScore(m.score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

/** 得分到百万级，表格里用「万」 */
function fmtScore(v: number | null): string {
  if (v == null) return "—";
  return v >= 10_000 ? `${(v / 10_000).toFixed(v >= 1_000_000 ? 0 : 1)} 万` : fmtFull(v);
}

/** 最常玩的地图：前 6 张，地图图片 + 时长和占比，点开进图鉴 */
export function MapsPanel({ maps, game }: { maps: CareerMap[]; game: string }) {
  if (!maps.length) return null;
  const total = maps.reduce((sum, m) => sum + m.time_seconds, 0);
  return (
    <Panel>
      <SectionHeading className="mb-4">常玩地图</SectionHeading>
      <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-2">
        {maps.slice(0, 6).map((m) => (
          <li key={m.map}>
            <Link
              href={`/${game}/codex/maps/${m.map}`}
              prefetch={false}
              className="group compact-action block outline-none"
            >
              <div className="relative aspect-[16/9] overflow-hidden bg-black/40 ring-1 ring-white/10 transition-shadow group-hover:ring-amber-400/50 group-focus-visible:ring-amber-400/50">
                {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                <img
                  src={mapImage(m.map, 480)}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  className="size-full object-cover"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />
                <div className="absolute inset-x-0 bottom-0 p-2">
                  <div className="truncate text-[13px] leading-tight font-semibold text-white group-hover:text-amber-200">
                    {mapLabel(m.map)}
                  </div>
                  <div className="mt-0.5 flex justify-between gap-2 text-[11px] text-white/60 tabular-nums">
                    <span>{fmtHours(m.time_seconds)}</span>
                    <span>{fmtPct(m.time_seconds / total)}</span>
                  </div>
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** 精英兵：接在兵种表下面，只列玩过的 */
export function EliteKits({ kits }: { kits: EliteKitStat[] }) {
  if (!kits.length) return null;
  const rows = [...kits].sort((a, b) => b.time_seconds - a.time_seconds);
  return (
    <section className="mt-5 border-t border-white/10 pt-4">
      <div className="grid grid-cols-[minmax(0,1fr)_4.5rem_4rem_3.5rem] gap-x-4 px-1 pb-1.5 text-[11px] tracking-wider text-white/40">
        <span>精英兵</span>
        <span className="text-right">时长</span>
        <span className="text-right">击杀</span>
        <span className="text-right">KPM</span>
      </div>
      <ol>
        {rows.map((k) => (
          <li
            key={k.kit}
            className="grid grid-cols-[minmax(0,1fr)_4.5rem_4rem_3.5rem] gap-x-4 px-1 py-1 text-sm tabular-nums"
          >
            <span className="text-white">{ELITE_LABEL[k.kit] ?? k.kit}</span>
            <span className="text-right text-white/70">{formatDuration(k.time_seconds)}</span>
            <span className="text-right text-white/85">{fmtFull(k.kills)}</span>
            <span className="text-right text-white/70">
              {fmtFixed(perMinute(k.kills, k.time_seconds))}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
