"use client";

import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Trophy } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import {
  FactionFlag,
  RoundDetailView,
  formatRoundTime,
  roundDuration,
} from "@/components/bf1/rounds/RoundDetailView";
import { bf1Api, type RoundSummary } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 服务器对局：每局结算时把在服玩家的生涯和进服时对比，算出这一局各人的战绩。服重启前后的实例
 * 合在一起列，保留 90 天。上方一排地图卡片按结束时间从新到旧选局，下方整宽显示计分板。
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

      {items.length === 0 ? (
        <div className="flex min-h-[240px] items-center justify-center text-sm text-white/40">
          {list.isLoading
            ? "正在加载对局…"
            : list.isError
              ? "对局加载失败，请稍后重试"
              : "还没有记录到对局，每局结束后一两分钟出现在这里"}
        </div>
      ) : (
        <>
          <ol className="-mx-1 mt-4 flex snap-x gap-2 overflow-x-auto px-1 pb-2">
            {items.map((r) => (
              <RoundCard
                key={r.id}
                round={r}
                active={r.id === active?.id}
                onClick={() => setSelected(r.id)}
              />
            ))}
            {list.hasNextPage ? (
              <li className="shrink-0">
                <button
                  type="button"
                  disabled={list.isFetchingNextPage}
                  onClick={() => list.fetchNextPage()}
                  className="h-full w-24 rounded-sm border border-dashed border-white/20 text-xs text-white/60 hover:bg-white/10 disabled:opacity-50"
                >
                  {list.isFetchingNextPage ? "加载中…" : "更早的对局"}
                </button>
              </li>
            ) : null}
          </ol>
          {active ? (
            <div className="mt-4">
              <RoundDetailView roundId={active.id} game={game} />
            </div>
          ) : null}
        </>
      )}
    </Bf1Panel>
  );
}

function RoundCard({
  round: r,
  active,
  onClick,
}: {
  round: RoundSummary;
  active: boolean;
  onClick: () => void;
}) {
  const winner = r.winner === 1 ? r.team1_faction : r.winner === 2 ? r.team2_faction : null;
  return (
    <li className="shrink-0 snap-start">
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className={cn(
          "relative block h-[4.5rem] w-48 overflow-hidden rounded-sm border text-left transition-colors",
          active ? "border-amber-400" : "border-white/10 hover:border-white/30",
        )}
      >
        {r.map_image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={r.map_image_url}
            alt=""
            loading="lazy"
            className={cn(
              "absolute inset-0 h-full w-full object-cover transition-opacity",
              active ? "opacity-55" : "opacity-30",
            )}
          />
        ) : null}
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 to-black/30" />
        {active ? <span className="absolute inset-x-0 bottom-0 h-0.5 bg-amber-400" /> : null}
        {winner ? (
          <span
            className="absolute right-2 bottom-1.5 flex items-center gap-1 text-[10px] font-semibold text-amber-300"
            title={`${winner} 胜`}
          >
            <Trophy className="size-3.5" strokeWidth={2.5} aria-hidden />
            <FactionFlag faction={winner} className="size-6" />
          </span>
        ) : null}
        <div className="relative flex h-full flex-col justify-between px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2 text-[11px] text-white/70 tabular-nums">
            <span>{formatRoundTime(r.ended_at)}</span>
            <span className="text-white/50">{roundDuration(r)}</span>
          </div>
          <div>
            <div className="truncate text-sm font-semibold text-white">
              {r.map_display_name ?? r.map_name ?? "未知地图"}
            </div>
            <div className="flex gap-2 pr-10 text-[11px] text-white/55">
              {r.mode_display_name ? (
                <span className="truncate text-amber-300/80">{r.mode_display_name}</span>
              ) : null}
              <span className="shrink-0">{r.player_count} 人</span>
              {!r.settled ? <span className="shrink-0">未打完</span> : null}
            </div>
          </div>
        </div>
      </button>
    </li>
  );
}
