import { Skeleton } from "@/components/ui/skeleton";

/** 战绩查询页骨架：标题 + 大搜索框，与真实页面同宽（max-w-5xl）。 */
export default function PlayersLoading() {
  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
      <div className="space-y-3">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-12 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
      <Skeleton className="h-[88px] w-full" />
    </main>
  );
}
