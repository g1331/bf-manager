import { redirect } from "next/navigation";

// 账号设置已并入个人主页 /me。
export default function AccountRedirect() {
  redirect("/me");
}
