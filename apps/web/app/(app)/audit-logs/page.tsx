import { redirect } from "next/navigation";

// 个人操作日志已并入个人主页 /me；管理员的全平台审计在 /admin/audit。
export default function AuditLogsRedirect() {
  redirect("/me");
}
