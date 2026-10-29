"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronDown, Flag } from "lucide-react";
import { Panel } from "@/components/bf1/player-detail/CareerOverview";
import {
  FactionFlag,
  KitIcon,
  kitLabel,
  RoundDetailView,
  formatClock,
  roundDuration,
  roundHref,
} from "@/components/bf1/rounds/RoundDetailView";
import { mainWeapon } from "@/components/bf1/rounds/RoundPlayerBreakdown";
import { RowsSkeleton } from "@/components/layout/PageSkeleton";
import { bf1Api, type PlayerRound } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 玩家对局：我们跟踪到的每一局（私服和官服都有，保留 90 天），由这一局前后的生涯差值算出。
 * 按天分组；窄屏每局一张以地图为底的卡片，宽屏挂在左侧时间线上。点开看双方全员。
 */
export function PlayerRounds({ personaId, game }: { personaId: number; game: string }) {
  const [open, setOpen] = useState<number | null>(null);
  const list = useInfiniteQuery({
    queryKey: ["bf1-player-rounds", personaId],
    queryFn: ({ pageParam }) => bf1Api.getPlayerRounds(personaId, pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_before,
  });
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const groups = useMemo(() => groupByDay(items), [items]);

  if (list.isLoading) return <RowsSkeleton rows={6} />;
  if (items.length === 0)
    return (
      <Panel>
        <div className="py-8 text-center text-sm text-white/40">
          {list.isError ? "对局加载失败，请稍后重试" : "还没有记录到这位玩家的对局"}
        </div>
      </Panel>
    );
  return (
    <Panel>
      {/* 按列表自身宽度排版（侧栏会占掉宽度，视口断点测不准） */}
      <div className="@container space-y-5">
        {groups.map((g, i) => {
          const wins = g.items.filter((it) => outcomeOf(it.player) === "win").length;
          // 最后一天可能还有没加载的局，局数不全就不写
          const partial = i === groups.length - 1 && list.hasNextPage;
          return (
            <section key={g.key}>
              <h3 className="mb-2 flex items-baseline justify-between gap-3 text-xs font-bold tracking-[0.04em] text-white/80">
                {g.label}
                {partial ? null : (
                  <span className="text-[11px] font-normal tracking-normal text-white/40 tabular-nums">
                    {g.items.length} 局 · {wins} 胜
                  </span>
                )}
              </h3>
              <ol className="relative space-y-2 @2xl:space-y-2.5 @2xl:pl-5 @2xl:before:absolute @2xl:before:inset-y-1.5 @2xl:before:left-1 @2xl:before:w-px @2xl:before:bg-white/15">
                {g.items.map((it) => (
                  <li key={it.round.id} className="relative">
                    <RoundCard
                      item={it}
                      game={game}
                      expanded={open === it.round.id}
                      onToggle={() => setOpen(open === it.round.id ? null : it.round.id)}
                    />
                    {open === it.round.id ? (
                      <div className="border-x border-b border-white/10 bg-black/25 px-4 pt-4 pb-5">
                        <RoundDetailView roundId={it.round.id} game={game} highlight={personaId} />
                      </div>
                    ) : null}
                  </li>
                ))}
              </ol>
            </section>
          );
        })}
      </div>
      {list.hasNextPage ? (
        <button
          type="button"
          disabled={list.isFetchingNextPage}
          onClick={() => list.fetchNextPage()}
          className="mt-3 h-8 w-full rounded-sm border border-white/15 text-xs text-white/70 hover:bg-white/10 disabled:opacity-50"
        >
          {list.isFetchingNextPage ? "加载中…" : "加载更早的"}
        </button>
      ) : null}
      <p className="mt-3 text-[11px] text-white/35">
        只包含本站跟踪到的对局，私服和官服都有，保留 90 天。
      </p>
    </Panel>
  );
}

type DayGroup = { key: string; label: string; items: PlayerRound[] };

/** 列表已按结束时间从新到旧排好，相邻同一天的并成一组（按浏览器本地时区） */
function groupByDay(items: PlayerRound[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const it of items) {
    const d = new Date(it.round.ended_at * 1000);
    const key = d.toDateString();
    const last = groups.at(-1);
    if (last?.key === key) last.items.push(it);
    else groups.push({ key, label: dayLabel(d), items: [it] });
  }
  return groups;
}

function dayLabel(d: Date): string {
  const now = new Date();
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000);
  const date = `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  const full = d.getFullYear() === now.getFullYear() ? date : `${d.getFullYear()} 年 ${date}`;
  if (days === 0) return `今天 · ${full}`;
  if (days === 1) return `昨天 · ${full}`;
  return full;
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

type Outcome = "win" | "loss" | "left" | "unknown";

const OUTCOME: Record<
  Outcome,
  { label: string; text: string; bar: string; node: string; card: string; shade: string }
> = {
  win: {
    label: "胜利",
    text: "text-amber-400 tracking-[0.12em]",
    bar: "bg-amber-400",
    node: "bg-amber-400",
    card: "border-amber-400/40 bg-gradient-to-r from-amber-400/15 to-white/[0.04] to-45%",
    shade:
      "bg-[linear-gradient(90deg,rgba(40,28,4,0.92),rgba(20,16,10,0.75)_50%,rgba(14,16,19,0.15))]",
  },
  loss: {
    label: "失败",
    text: "text-white/60 tracking-[0.12em]",
    bar: "bg-white/30",
    node: "bg-[#6b6f76]",
    card: "border-white/10 bg-white/[0.045]",
    shade:
      "bg-[linear-gradient(90deg,rgba(14,16,19,0.94),rgba(14,16,19,0.78)_50%,rgba(14,16,19,0.25))]",
  },
  // 中途退出的战绩照样是真的（算到退出那一刻），只是整张卡淡一点
  left: {
    label: "中途退出",
    text: "text-white/50 tracking-[0.04em]",
    bar: "bg-white/15",
    node: "border border-white/40 bg-[#15171a]",
    card: "border-white/10 bg-white/[0.045] opacity-60 hover:opacity-100",
    shade:
      "bg-[linear-gradient(90deg,rgba(14,16,19,0.94),rgba(14,16,19,0.78)_50%,rgba(14,16,19,0.25))]",
  },
  unknown: {
    label: "胜负不明",
    text: "text-white/50 tracking-[0.04em]",
    bar: "bg-white/15",
    node: "bg-[#6b6f76]",
    card: "border-white/10 bg-white/[0.045]",
    shade:
      "bg-[linear-gradient(90deg,rgba(14,16,19,0.94),rgba(14,16,19,0.78)_50%,rgba(14,16,19,0.25))]",
  },
};

function outcomeOf(p: PlayerRound["player"]): Outcome {
  if (p.status === "left") return "left";
  if (p.won == null) return "unknown";
  return p.won ? "win" : "loss";
}

function RoundCard({
  item: { round: r, player: p },
  game,
  expanded,
  onToggle,
}: {
  item: PlayerRound;
  game: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const outcome = outcomeOf(p);
  const o = OUTCOME[outcome];
  const faction = p.team === 1 ? r.team1_faction : r.team2_faction;
  const mapName = r.map_display_name ?? r.map_name ?? "未知地图";
  const main = mainWeapon(p);

  const flag = (className: string) =>
    faction ? (
      <FactionFlag
        faction={faction}
        won={outcome === "left" ? false : p.won}
        className={className}
      />
    ) : (
      <span
        className={cn("flex items-center justify-center text-white/25", className)}
        title="阵营未知"
      >
        <Flag className="size-5" />
      </span>
    );
  const title = (
    <div className="truncate text-[15px] font-bold text-white">
      {mapName}
      {r.mode_display_name ? (
        <span className="ml-1.5 text-[11px] font-medium text-amber-300/85">
          {r.mode_display_name}
        </span>
      ) : null}
    </div>
  );
  const result = (
    <span className={cn("text-[11px] leading-none font-extrabold whitespace-nowrap", o.text)}>
      {o.label}
    </span>
  );
  // 服务器名点了跳到服务器详情里的这一局，所以单独可点，不能嵌在 button 里
  const server = (className: string) =>
    r.server_name ? (
      <Link
        href={roundHref(game, r)}
        title="在服务器详情里查看这一局"
        className={cn(
          "inline-action pointer-events-auto relative block max-w-full truncate text-[11px] text-white/50 underline-offset-2 transition-colors hover:text-amber-300 hover:underline",
          className,
        )}
      >
        {r.server_name}
      </Link>
    ) : null;
  const chevron = (
    <ChevronDown
      className={cn(
        "size-4 shrink-0 text-white/30 transition-transform group-hover:text-white",
        expanded && "rotate-180",
      )}
    />
  );
  const stats = (
    <>
      <Stat label="击杀 / 死亡" value={`${p.kills} / ${p.deaths}`} />
      <Stat label="得分" value={p.score.toLocaleString("en-US")} />
      <Stat label="SPM" value={p.spm ?? "—"} />
      <Stat label="K/D" value={p.kd != null ? p.kd.toFixed(2) : "—"} />
    </>
  );

  return (
    <>
      {/* 宽屏：时间挂在左侧竖线上 */}
      <span
        aria-hidden
        className={cn("absolute top-[3px] -left-5 hidden size-[9px] @2xl:block", o.node)}
      />
      <div className="mb-1 hidden text-[11px] text-white/55 tabular-nums @2xl:block">
        {formatClock(r.ended_at)} · {roundDuration(r)}
      </div>

      <div
        className={cn(
          "group relative overflow-hidden border transition-[border-color,opacity] hover:border-white/25",
          o.card,
          expanded && "border-white/25 opacity-100",
        )}
      >
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={`${mapName} 对局详情`}
          className="absolute inset-0"
        />

        {/* 窄屏：地图铺在上半截当底，下面一行战绩 */}
        <div className="pointer-events-none @2xl:hidden">
          <div
            className="relative bg-cover bg-[center_40%] py-2.5 pr-2.5 pl-3.5"
            style={r.map_image_url ? { backgroundImage: `url(${r.map_image_url})` } : undefined}
          >
            <div className={cn("absolute inset-0", o.shade)} />
            <div className="relative flex items-center gap-2.5">
              {flag("size-[30px]")}
              <div className="min-w-0 flex-1">
                {title}
                <div className="mt-0.5 truncate text-[11px] text-white/55">
                  {formatClock(r.ended_at)} · {roundDuration(r)}
                  {faction ? ` · ${faction}` : ""}
                </div>
              </div>
              <span className="drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]">{result}</span>
              {chevron}
            </div>
            {server("mt-1.5")}
          </div>
          <dl className="grid grid-cols-[1.25fr_1fr_0.9fr_0.8fr] gap-x-2 border-t border-white/[0.06] py-2 pr-2.5 pl-3.5 tabular-nums">
            {stats}
          </dl>
        </div>

        {/* 宽屏：缩略图 + 地图兵种武器 + 战绩 + 胜负阵营 */}
        <div className="pointer-events-none hidden items-center gap-3 pr-2.5 @2xl:flex">
          <div className="h-[62px] w-24 shrink-0 bg-white/[0.06]">
            {r.map_image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={r.map_image_url}
                alt=""
                loading="lazy"
                className="h-full w-full object-cover"
              />
            ) : null}
          </div>
          <div className="min-w-0 flex-1 py-1.5">
            {title}
            <div className="mt-1 flex items-center gap-1.5 text-[11px] whitespace-nowrap text-white/50">
              <KitIcon kit={p.kit} className="size-3.5" />
              <span className="shrink-0">{kitLabel(p.kit)}</span>
              {main ? (
                <span className="min-w-0 truncate" title={main.name ?? undefined}>
                  · {main.name ?? "未知"}
                  {main.kills ? ` · ${main.kills} 杀` : ""}
                </span>
              ) : null}
            </div>
            {server("mt-0.5")}
          </div>
          <dl className="grid shrink-0 grid-cols-[4rem_3.75rem_3rem_2.75rem] gap-x-2.5 text-right tabular-nums">
            {stats}
          </dl>
          <div className="flex w-[5.5rem] shrink-0 items-center justify-end gap-2">
            {result}
            {flag("size-[30px]")}
          </div>
          {chevron}
        </div>

        {/* 窄屏左边的胜负色条 */}
        <span
          className={cn("pointer-events-none absolute inset-y-0 left-0 w-[3px] @2xl:hidden", o.bar)}
        />
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-[10px] whitespace-nowrap text-white/40">{label}</dt>
      <dd className="text-[15px] font-semibold whitespace-nowrap text-white">{value}</dd>
    </div>
  );
}
