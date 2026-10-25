"use client";

import { useQuery } from "@tanstack/react-query";
import { TrendPanel } from "@/components/bf1/visual/TrendPanel";
import { bf1Api } from "@/lib/api/bf1";

/**
 * 服务器详情页的 24 小时人数曲线。只有私服才有采样（全服统计每分钟一点，空服不记），
 * 没有任何采样时整块不渲染，避免给官服和一直没人的服展示空面板。
 */
export function ServerPlayerTrend({ gameId }: { gameId: number }) {
  const counts = useQuery({
    queryKey: ["bf1-server-player-counts", gameId],
    queryFn: () => bf1Api.getServerPlayerCounts(gameId),
    refetchInterval: 60_000,
  });

  if (!counts.data?.length) return null;
  return (
    <div className="mt-6">
      <TrendPanel
        title="24 小时人数"
        points={counts.data}
        emptyText="人数采集中，每分钟记录一次，稍后可见曲线。"
        describe={(p) => `排队 ${p.queue} · 观战 ${p.spectators}`}
      />
    </div>
  );
}
