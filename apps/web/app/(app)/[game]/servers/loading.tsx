import { Skeleton } from "@/components/ui/skeleton";
import { ServerListSkeleton } from "@/components/layout/PageSkeleton";

/**
 * 服务器浏览器骨架：标题行 + 子标签 + 「左密集列表 + 右 300px 筛选面板」双栏，
 * 与真实页面的 flex/grid 结构一致，内容就绪时左右两栏不发生布局跳动。
 */
export default function ServersLoading() {
  return (
    <main className="flex flex-col gap-4 py-6 text-white lg:h-full lg:min-h-0">
      {/* 标题行 */}
      <header className="flex flex-wrap items-end justify-between gap-3 lg:shrink-0">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="h-[2px] w-6 bg-amber-500/70" />
            <Skeleton className="h-3 w-14" />
          </div>
          <Skeleton className="h-8 w-48 sm:h-9" />
        </div>
        <Skeleton className="h-5 w-40" />
      </header>

      {/* 子标签行 */}
      <div className="flex items-center gap-6">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-5 w-16" />
        ))}
      </div>

      {/* 左列表 + 右筛选面板 */}
      <div className="grid grid-cols-1 gap-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_300px]">
        <ServerListSkeleton />
        <Skeleton className="hidden h-full min-h-64 lg:block" />
      </div>
    </main>
  );
}
