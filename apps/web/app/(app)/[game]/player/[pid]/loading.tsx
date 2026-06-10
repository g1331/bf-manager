import { PlayerDetailSkeleton } from "@/components/layout/PageSkeleton";

/** 玩家详情路由的 loading 边界：与页面内 statsQ.isLoading 分支共用同一骨架。 */
export default function PlayerDetailLoading() {
  return <PlayerDetailSkeleton />;
}
