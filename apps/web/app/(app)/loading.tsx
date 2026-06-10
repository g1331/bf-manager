import { PageHeaderSkeleton, RowsSkeleton } from "@/components/layout/PageSkeleton";

/**
 * (app) 组的兜底 loading 边界：没有专属骨架的页面（我的主页、重定向中转页等）
 * 在导航提交后立即显示此骨架，使点击导航即时响应而非冻结等待 RSC 返回。
 * 高频页面（概况 / 服务器 / 战绩 / 管理后台）各自有更贴合版式的专属 loading.tsx。
 */
export default function AppLoading() {
  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      <PageHeaderSkeleton />
      <RowsSkeleton rows={6} />
    </main>
  );
}
