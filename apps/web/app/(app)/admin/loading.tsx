import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";

/**
 * 管理后台各页（运维概览 / EA 账号池 / 服管权限 / 审计日志）的共享 loading 边界，
 * 与各页 useSession 门控期间的占位共用同一骨架。
 */
export default function AdminLoading() {
  return <AdminPageSkeleton />;
}
