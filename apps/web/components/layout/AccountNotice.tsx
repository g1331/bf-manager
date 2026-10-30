"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "@/hooks/useSession";

/**
 * 账号状态守门：
 * - 还没绑 EA 的账号（pending_binding）一进应用就送去绑定页，站内接口对它一律 403；
 * - remid 登录时代的旧账号（legacy）顶部挂一条提醒，引导去「我的」设置登录邮箱。
 */
export function AccountNotice() {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const status = session.data?.status;

  useEffect(() => {
    if (status === "pending_binding") router.replace("/bind");
  }, [status, router]);

  if (status !== "legacy" || pathname === "/me") return null;
  return (
    <div className="mx-4 mt-3 rounded-sm border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm leading-relaxed text-amber-100 sm:mx-10">
      remid 登录已经停用。
      <Link
        href="/me"
        className="ml-1 font-medium text-amber-400 underline-offset-4 hover:underline"
      >
        设置登录邮箱
      </Link>
      ，以后用邮箱和密码登录；不设置的话，当前登录过期后要用 EA 账号邮箱重新注册认领。
    </div>
  );
}
