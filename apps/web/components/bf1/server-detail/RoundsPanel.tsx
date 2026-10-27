"use client";

import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import {
  RoundDetailView,
  formatRoundTime,
  roundDuration,
} from "@/components/bf1/rounds/RoundDetailView";
import { bf1Api, type RoundSummary } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 服务器对局：每局结算时把在服玩家的生涯和进服时对比，算出这一局各人的战绩。服重启前后的实例
 * 合在一起列，保留 90 天。左侧按结束时间列出对局，右侧看两队明细。
 */
export function RoundsPanel({ gameId, game }: { gameId: number; game: string }) {
  const [selected, setSelected] = useState<number | null>(null);
  const list = useInfiniteQuery({
    queryKey: ["bf1-server-rounds", gameId],
    queryFn: ({ pageParam }) => bf1Api.getServerRounds(gameId, pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_before,
    refetchInterval: 60_000,
  });
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const active = items.find((r) => r.id === selected) ?? items[0] ?? null;

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="bg-black/45 p-5 backdrop-blur-sm sm:p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <SectionHeading className="mb-0">对局</SectionHeading>
        <span className="text-[11px] text-white/40">由每局前后的生涯差值算出 · 保留 90 天</span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col">
          <ol className="max-h-[680px] space-y-1.5 overflow-y-auto pr-1">
            {items.map((r) => (
              <RoundItem
                key={r.id}
                round={r}
                active={r.id === active?.id}
                onClick={() => setSelected(r.id)}
              />
            ))}
            {!list.isLoading && items.length === 0 ? (
              <li className="py-8 text-center text-xs text-white/40">
                {list.isError ? "对局加载失败，请稍后重试" : "还没有记录到对局"}
              </li>
            ) : null}
          </ol>
          {list.hasNextPage ? (
            <button
              type="button"
              disabled={list.isFetchingNextPage}
              onClick={() => list.fetchNextPage()}
              className="mt-2 h-8 rounded-sm border border-white/15 text-xs text-white/70 hover:bg-white/10 disabled:opacity-50"
            >
              {list.isFetchingNextPage ? "加载中…" : "加载更早的"}
            </button>
          ) : null}
        </aside>

        {active ? (
          <RoundDetailView roundId={active.id} game={game} />
        ) : (
          <div className="flex min-h-[240px] items-center justify-center text-sm text-white/40">
            {list.isLoading ? "正在加载对局…" : "每局结束后一两分钟出现在这里"}
          </div>
        )}
      </div>
    </Bf1Panel>
  );
}

function RoundItem({
  round: r,
  active,
  onClick,
}: {
  round: RoundSummary;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "w-full rounded-sm border px-3 py-2 text-left transition-colors",
          active
            ? "border-amber-400/60 bg-amber-400/10"
            : "border-white/10 bg-white/[0.03] hover:bg-white/[0.07]",
        )}
      >
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="text-white/75 tabular-nums">{formatRoundTime(r.ended_at)}</span>
          <span className="text-white/45 tabular-nums">{roundDuration(r)}</span>
        </div>
        <div className="mt-0.5 truncate text-sm font-semibold text-white">
          {r.map_display_name ?? r.map_name ?? "未知地图"}
        </div>
        <div className="mt-0.5 flex gap-2.5 text-[11px] text-white/50">
          {r.mode_display_name ? <span>{r.mode_display_name}</span> : null}
          <span>{r.player_count} 人</span>
          {!r.settled ? <span>未打完</span> : null}
        </div>
      </button>
    </li>
  );
}
