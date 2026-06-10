import { ServerDetailSkeleton } from "@/components/layout/PageSkeleton";

/** 服务器详情路由的 loading 边界：与页面内 detail.isLoading 分支共用同一骨架。 */
export default function ServerDetailLoading() {
  return <ServerDetailSkeleton />;
}
