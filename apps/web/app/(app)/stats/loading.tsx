import { Skeleton } from "@/components/ui/skeleton";
import { PageHeaderSkeleton, StatsOverviewSkeleton } from "@/components/layout/PageSkeleton";

/** 全服统计（概况）页骨架：标题 + 指标面板区 + 底部两张入口卡，对齐真实版式。 */
export default function StatsLoading() {
  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      <PageHeaderSkeleton />
      <StatsOverviewSkeleton />
      {/* 底部入口卡（战绩查询 / 服务器） */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-36 w-full" />
      </section>
    </main>
  );
}
