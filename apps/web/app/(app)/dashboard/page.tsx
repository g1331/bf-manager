import { redirect } from "next/navigation";

// 门户改版后仪表盘内容已拆分：公共统计→/stats、个人信息→/me、运维概览→/admin。
// 旧入口统一跳转到公共统计页。
export default function DashboardRedirect() {
  redirect("/stats");
}
