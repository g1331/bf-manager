"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  CircleUser,
  Gamepad2,
  Gauge,
  KeyRound,
  ScrollText,
  Server,
  ShieldCheck,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ENABLED_GAMES } from "@/lib/game-registry";
import { useSession } from "@/hooks/useSession";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  /** 高亮采用精确匹配（用于本身是其它路由前缀的入口，如运维概览 /admin）。 */
  exact?: boolean;
  /**
   * 额外参与高亮匹配的路由前缀。用于列表入口（复数 /players、/servers）覆盖其
   * 对应的单数详情页（/player/:id、/server/:id），使从列表点进详情后入口仍高亮。
   */
  match?: string[];
}

interface NavGroup {
  title?: string;
  items: NavItem[];
  /** 仅平台管理员可见。 */
  adminOnly?: boolean;
  /** 仅登录用户可见。 */
  authOnly?: boolean;
}

function buildNavGroups(): NavGroup[] {
  const gameItems: NavItem[] = ENABLED_GAMES.flatMap((g) => [
    {
      label: `${g.shortName} 战绩查询`,
      href: `/${g.id}/players`,
      icon: Users,
      match: [`/${g.id}/player`],
    },
    {
      label: `${g.shortName} 服务器`,
      href: `/${g.id}/servers`,
      icon: Server,
      match: [`/${g.id}/server`],
    },
  ]);

  return [
    {
      title: "总览",
      items: [
        { label: "全站统计", href: "/stats", icon: BarChart3 },
        ...(gameItems.length > 0
          ? gameItems
          : [{ label: "暂无可用游戏", href: "#", icon: Gamepad2 }]),
      ],
    },
    {
      title: "个人",
      authOnly: true,
      items: [{ label: "我的主页", href: "/me", icon: CircleUser }],
    },
    {
      title: "管理",
      adminOnly: true,
      items: [
        { label: "运维概览", href: "/admin", icon: Gauge, exact: true },
        { label: "EA 账号池", href: "/admin/ea-accounts", icon: KeyRound },
        { label: "服管权限", href: "/admin/memberships", icon: ShieldCheck },
        { label: "审计日志", href: "/admin/audit", icon: ScrollText },
      ],
    },
  ];
}

const NAV_GROUPS = buildNavGroups();

function isActive(pathname: string, item: NavItem): boolean {
  if (item.href === "#") return false;
  if (item.exact) return pathname === item.href;
  const prefixes = [item.href, ...(item.match ?? [])];
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

interface AppSidebarProps {
  onNavClick?: () => void;
}

export function AppSidebar({ onNavClick }: AppSidebarProps) {
  const pathname = usePathname();
  const session = useSession();
  const isLoggedIn = !!session.data;
  const isAdmin = session.data?.role === "admin";

  return (
    <nav className="flex h-full flex-col gap-1 px-3 py-4">
      <Link href="/stats" className="mb-6 flex items-center gap-2.5 px-3" onClick={onNavClick}>
        <span className="h-5 w-[3px] shrink-0 bg-amber-500" />
        <span className="font-display text-base font-semibold tracking-[0.18em] text-white uppercase">
          BF-Manager
        </span>
      </Link>

      {NAV_GROUPS.map((group) => {
        if (group.adminOnly && !isAdmin) return null;
        if (group.authOnly && !isLoggedIn) return null;
        return (
          <div key={group.title ?? "_main"} className="mt-2">
            {group.title ? (
              <div className="mb-1.5 px-3 text-[11px] font-medium tracking-[0.18em] text-amber-500/90 uppercase">
                {group.title}
              </div>
            ) : null}
            {group.items.map((item) => {
              const active = isActive(pathname, item);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavClick}
                  className={cn(
                    "relative flex items-center gap-3 rounded-sm px-3 py-2 text-sm transition-colors",
                    "before:absolute before:top-1/2 before:left-0 before:h-5 before:w-[3px] before:-translate-y-1/2 before:bg-amber-500 before:transition-opacity",
                    active
                      ? "bg-amber-500/10 font-medium text-amber-500 before:opacity-100"
                      : "text-muted-foreground hover:text-foreground before:opacity-0 hover:bg-white/5",
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
