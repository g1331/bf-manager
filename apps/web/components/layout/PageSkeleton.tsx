import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * 路由级与页面级共用的骨架屏组成件。
 *
 * 双层使用场景：
 * 1. 各路由段的 loading.tsx——Next.js 有了 loading 边界后，点击导航会立即提交并
 *    渲染骨架，不再等待 RSC 响应往返（「点击 tab 卡顿几秒才跳转」的根治手段）；
 * 2. 页面内 react-query 的 isLoading 分支——与路由骨架同形，避免出现
 *    「骨架 → 加载中文本 → 内容」的二次跳变。
 * 骨架版式刻意对齐真实页面的行高与栅格，让内容就绪时的替换尽量不发生布局跳动。
 */

/** PageHeader 的骨架版：kicker 刻线 + 主标题 + 描述，行高与真实组件对齐。 */
export function PageHeaderSkeleton({ className }: { className?: string }) {
  return (
    <header className={cn("space-y-2", className)}>
      <div className="flex items-center gap-2">
        <span className="h-[2px] w-6 bg-amber-500/70" />
        <Skeleton className="h-3 w-16" />
      </div>
      <Skeleton className="h-8 w-44 sm:h-9" />
      <Skeleton className="h-4 w-72 max-w-full" />
    </header>
  );
}

/** 通用列表行骨架：行高对齐应用内密集表格行。 */
export function RowsSkeleton({ rows = 8, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

/** 全服统计（概况）的指标区骨架：总览数字四宫格 + 两块分布面板。 */
export function StatsOverviewSkeleton() {
  return (
    <section className="space-y-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    </section>
  );
}

/** 服务器浏览器的列表区骨架：常驻表头 + 密集行。 */
export function ServerListSkeleton({ rows = 12 }: { rows?: number }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Skeleton className="h-6 w-full" />
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

/**
 * 服务器详情页整页骨架：返回行 + 信息横幅 + 标签行 + 玩家双列。
 * 真实页面的全屏地图背景属于数据态内容，骨架阶段由底层战场氛围透出即可，
 * 不在此铺 fixed 层。
 */
export function ServerDetailSkeleton() {
  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <div className="relative z-10 max-w-[1600px] px-6 py-5 sm:px-10 sm:py-8">
        <Skeleton className="mb-4 h-5 w-24" />
        <Skeleton className="h-40 w-full sm:h-48" />
        <div className="mt-6 flex items-center gap-6">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-5 w-16" />
          ))}
        </div>
        <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {Array.from({ length: 2 }, (_, col) => (
            <div key={col} className="space-y-2">
              <Skeleton className="h-8 w-full" />
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 玩家详情页整页骨架：生涯横幅（头像 + 昵称）+ 统计面板网格 + 分区块。 */
export function PlayerDetailSkeleton() {
  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <div className="relative z-10 max-w-[1600px] px-6 py-5 sm:px-10 sm:py-8">
        <div className="flex items-center gap-4">
          <Skeleton className="size-16 rounded-full sm:size-20" />
          <div className="space-y-2">
            <Skeleton className="h-7 w-48" />
            <Skeleton className="h-4 w-32" />
          </div>
        </div>
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <div className="mt-8 space-y-3">
          <Skeleton className="h-6 w-32" />
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * 管理后台页骨架（max-w-6xl）：标题 + 概要块 + 表格行。
 * 同时用作各 admin 页 useSession 门控期间的占位（取代「加载中…」文本）。
 */
export function AdminPageSkeleton() {
  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeaderSkeleton />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
      <RowsSkeleton rows={8} />
    </main>
  );
}

/** 武器 / 载具卡片网格骨架：对齐详情页 tab 内容的三列卡片栅格。 */
export function CardGridSkeleton({ cards = 6 }: { cards?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: cards }, (_, i) => (
        <Skeleton key={i} className="h-32 w-full" />
      ))}
    </div>
  );
}
