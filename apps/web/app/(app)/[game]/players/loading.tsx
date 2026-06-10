import { Skeleton } from "@/components/ui/skeleton";
import { PageHeaderSkeleton } from "@/components/layout/PageSkeleton";

/** 玩家战绩查询页骨架：标题 + 搜索框行，与真实页面同宽（max-w-3xl）。 */
export default function PlayersLoading() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeaderSkeleton />
      <div className="flex gap-2">
        <Skeleton className="h-9 flex-1" />
        <Skeleton className="h-9 w-20" />
      </div>
    </main>
  );
}
