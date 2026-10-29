"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CircleUser,
  LayoutDashboard,
  Search,
  Server,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { isTabActive, type TopTab } from "@/lib/nav";

/**
 * 手机端底部标签栏：放最常用的五个入口，单手拇指就能够到。
 * 汉堡抽屉（一级模块）和顶部二级 tab 照旧保留，管理后台、战队、交换、行动仍从那里进。
 * 未登录时「我的服务器」「我的」由各自页面提示或跳转登录。
 * 高度 h-14（不含底部安全区），SidebarLayout 的内容区按这个高度留出底部空白。
 */
const ITEMS: (TopTab & { icon: LucideIcon })[] = [
  { label: "概况", href: "/stats", exact: true, icon: LayoutDashboard },
  { label: "服务器", href: "/bf1/servers", match: ["/bf1/server"], icon: Server },
  { label: "战绩", href: "/bf1/players", match: ["/bf1/player"], icon: Search },
  { label: "我的服务器", href: "/bf1/my-servers", icon: ShieldCheck },
  { label: "我的", href: "/me", icon: CircleUser },
];

export function MobileTabBar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="底部导航"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-black/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
    >
      <ul className="flex h-14">
        {ITEMS.map((item) => {
          const active = isTabActive(pathname, item);
          const Icon = item.icon;
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex h-full flex-col items-center justify-center gap-1 text-[11px] transition-colors",
                  // 激活态沿用侧边抽屉的琥珀色刻线语汇，刻线放在顶边
                  "before:absolute before:top-0 before:left-1/2 before:h-[2px] before:w-8 before:-translate-x-1/2 before:bg-amber-500 before:transition-opacity",
                  active ? "text-amber-500 before:opacity-100" : "text-white/60 before:opacity-0",
                )}
              >
                <Icon className="size-5" />
                <span className="leading-none whitespace-nowrap">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
