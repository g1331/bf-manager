"use client";

import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronDown, Flag } from "lucide-react";
import { Panel } from "@/components/bf1/player-detail/CareerOverview";
import {
  FactionFlag,
  KitTag,
  RoundDetailView,
  formatRoundTime,
  roundDuration,
} from "@/components/bf1/rounds/RoundDetailView";
import { RowsSkeleton } from "@/components/layout/PageSkeleton";
import { bf1Api, type PlayerRound } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 玩家对局：我们跟踪到的每一局（私服和官服都有，保留 90 天），由这一局前后的生涯差值算出。
 * 每局一张卡片，左侧是所在阵营的旗帜和胜负，点开看双方全员。
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
      <ol className="space-y-2">
        {items.map((it) => (
          <li key={it.round.id}>
            <RoundCard
              item={it}
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

type Outcome = "win" | "loss" | "left" | "unknown";

const OUTCOME: Record<Outcome, { label: string; text: string; bar: string; tint: string }> = {
  win: {
    label: "胜利",
    text: "text-amber-400",
    bar: "bg-amber-400",
    tint: "from-amber-400/20",
  },
  loss: { label: "失败", text: "text-white/60", bar: "bg-white/30", tint: "from-white/[0.07]" },
  left: { label: "中途退出", text: "text-white/45", bar: "bg-white/15", tint: "from-white/[0.04]" },
  unknown: {
    label: "胜负不明",
    text: "text-white/45",
    bar: "bg-white/15",
    tint: "from-white/[0.04]",
  },
};

function outcomeOf(p: PlayerRound["player"]): Outcome {
  if (p.status === "left") return "left";
  if (p.won == null) return "unknown";
  return p.won ? "win" : "loss";
}

function RoundCard({
  item: { round: r, player: p },
  expanded,
  onToggle,
}: {
  item: PlayerRound;
  expanded: boolean;
  onToggle: () => void;
}) {
  const o = OUTCOME[outcomeOf(p)];
  const faction = p.team === 1 ? r.team1_faction : r.team2_faction;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={cn(
        "group relative flex w-full items-center gap-4 overflow-hidden border border-white/10 bg-gradient-to-r to-transparent to-45% py-2.5 pr-3 pl-4 text-left transition-colors hover:border-white/25",
        o.tint,
        expanded && "border-white/25",
      )}
    >
      <span className={cn("absolute inset-y-0 left-0 w-1", o.bar)} />

      {/* 阵营旗帜 + 胜负 */}
      <div className="flex w-[4.5rem] shrink-0 flex-col items-center gap-0.5">
        {faction ? (
          <FactionFlag faction={faction} className="size-9" />
        ) : (
          <span className="flex size-9 items-center justify-center text-white/25" title="阵营未知">
            <Flag className="size-5" />
          </span>
        )}
        <span className={cn("font-display text-sm leading-none font-bold tracking-wide", o.text)}>
          {o.label}
        </span>
      </div>

      {/* 地图缩略图 */}
      <div className="relative hidden h-12 w-20 shrink-0 overflow-hidden [clip-path:polygon(0_0,100%_0,100%_calc(100%-8px),calc(100%-8px)_100%,0_100%)] sm:block">
        {r.map_image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={r.map_image_url} alt="" loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <div className="h-full w-full bg-white/[0.06]" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-[15px] font-semibold text-white">
          {r.map_display_name ?? r.map_name ?? "未知地图"}
          {r.mode_display_name ? (
            <span className="ml-2 text-xs font-medium text-amber-300/80">
              {r.mode_display_name}
            </span>
          ) : null}
        </div>
        <div className="mt-0.5 truncate text-xs text-white/45">
          {formatRoundTime(r.ended_at)} · {roundDuration(r)}
          {faction ? ` · ${faction}` : ""}
          {r.server_name ? ` · ${r.server_name}` : ""}
        </div>
      </div>

      <div className="hidden w-10 shrink-0 text-right md:block">
        <div className="text-[10px] text-white/40">兵种</div>
        <KitTag kit={p.kit} className="text-[15px] font-semibold" />
      </div>

      <dl className="grid shrink-0 grid-cols-3 gap-x-5 text-right tabular-nums sm:grid-cols-4">
        <Stat label="击杀 / 死亡" value={`${p.kills} / ${p.deaths}`} />
        <Stat label="得分" value={p.score.toLocaleString("en-US")} />
        <Stat label="SPM" value={p.spm ?? "—"} />
        <Stat
          label="K/D"
          value={p.kd != null ? p.kd.toFixed(2) : p.kills ? "∞" : "—"}
          className="hidden sm:block"
        />
      </dl>
      <ChevronDown
        className={cn(
          "size-4 shrink-0 text-white/30 transition-transform group-hover:text-white",
          expanded && "rotate-180",
        )}
      />
    </button>
  );
}

function Stat({
  label,
  value,
  className,
}: {
  label: string;
  value: string | number;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="text-[10px] whitespace-nowrap text-white/40">{label}</dt>
      <dd className="text-[15px] font-semibold whitespace-nowrap text-white">{value}</dd>
    </div>
  );
}
