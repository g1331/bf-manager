"use client";

import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { Panel } from "@/components/bf1/player-detail/CareerOverview";
import {
  KitIcon,
  RoundDetailView,
  formatRoundTime,
  kitLabel,
  roundDuration,
} from "@/components/bf1/rounds/RoundDetailView";
import { RowsSkeleton } from "@/components/layout/PageSkeleton";
import { bf1Api, type PlayerRound } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 玩家对局：我们跟踪到的每一局（私服和官服都有，保留 90 天），由这一局前后的生涯差值算出。
 * 点开一局看双方全员。
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
      <ol className="divide-y divide-white/[0.06]">
        {items.map((it) => (
          <li key={it.round.id}>
            <RoundRow
              item={it}
              expanded={open === it.round.id}
              onToggle={() => setOpen(open === it.round.id ? null : it.round.id)}
            />
            {open === it.round.id ? (
              <div className="border-t border-white/[0.06] px-1 pt-4 pb-5">
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

function RoundRow({
  item: { round: r, player: p },
  expanded,
  onToggle,
}: {
  item: PlayerRound;
  expanded: boolean;
  onToggle: () => void;
}) {
  const result = p.status === "left" ? "退出" : p.won == null ? "—" : p.won ? "胜" : "负";
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className="group flex w-full items-center gap-4 px-1 py-3 text-left transition-colors hover:bg-white/[0.04]"
    >
      <span
        className={cn(
          "w-9 shrink-0 rounded-sm py-0.5 text-center text-xs font-semibold",
          p.won ? "bg-amber-400 text-black" : "bg-white/10 text-white/60",
        )}
      >
        {result}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium text-white">
          {r.map_display_name ?? r.map_name ?? "未知地图"}
          {r.mode_display_name ? (
            <span className="text-amber-300/80"> · {r.mode_display_name}</span>
          ) : null}
        </div>
        <div className="mt-0.5 truncate text-xs text-white/45">
          {formatRoundTime(r.ended_at)} · {roundDuration(r)}
          {r.server_name ? ` · ${r.server_name}` : ""}
        </div>
      </div>
      <div className="hidden items-center gap-1.5 text-xs text-white/55 sm:flex">
        <KitIcon kit={p.kit} />
        {kitLabel(p.kit)}
      </div>
      <dl className="grid shrink-0 grid-cols-3 gap-x-4 text-right text-xs tabular-nums sm:grid-cols-4">
        <Num label="击杀/死亡" value={`${p.kills}/${p.deaths}`} />
        <Num label="得分" value={p.score.toLocaleString("en-US")} />
        <Num label="SPM" value={p.spm ?? "—"} />
        <Num label="KD" value={p.kd != null ? p.kd.toFixed(2) : "—"} className="hidden sm:block" />
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

function Num({
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
      <dt className="text-[10px] text-white/35">{label}</dt>
      <dd className="text-white">{value}</dd>
    </div>
  );
}
