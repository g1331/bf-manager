"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Gamepad2,
  KeyRound,
  LayoutDashboard,
  ScrollText,
  Server,
  ShieldCheck,
  UserCog,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ENABLED_GAMES } from "@/lib/game-registry";
import { useSession } from "@/hooks/useSession";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

interface NavGroup {
  title?: string;
  items: NavItem[];
  adminOnly?: boolean;
}

function buildNavGroups(): NavGroup[] {
  const gameItems: NavItem[] = ENABLED_GAMES.flatMap((g) => [
    { label: `${g.shortName} 战绩查询`, href: `/${g.id}/players`, icon: Users },
    { label: `${g.shortName} 服务器`, href: `/${g.id}/servers`, icon: Server },
  ]);

  return [
    {
      items: [{ label: "仪表盘", href: "/dashboard", icon: LayoutDashboard }],
    },
    {
      title: "游戏",
      items:
        gameItems.length > 0 ? gameItems : [{ label: "暂无可用游戏", href: "#", icon: Gamepad2 }],
    },
    {
      title: "账号",
      items: [
        { label: "账号设置", href: "/account", icon: UserCog },
        { label: "操作日志", href: "/audit-logs", icon: ScrollText },
      ],
    },
    {
      title: "管理",
      adminOnly: true,
      items: [
        { label: "服管权限", href: "/admin/memberships", icon: ShieldCheck },
        { label: "EA 账号", href: "/admin/ea-accounts", icon: KeyRound },
      ],
    },
  ];
}

const NAV_GROUPS = buildNavGroups();

interface AppSidebarProps {
  onNavClick?: () => void;
}

export function AppSidebar({ onNavClick }: AppSidebarProps) {
  const pathname = usePathname();
  const session = useSession();
  const isAdmin = session.data?.role === "admin";

  return (
    <nav className="flex h-full flex-col gap-1 px-3 py-4">
      <Link href="/dashboard" className="mb-6 flex items-center gap-2.5 px-3" onClick={onNavClick}>
        <span className="h-5 w-[3px] shrink-0 bg-amber-500" />
        <span className="font-display text-base font-semibold tracking-[0.18em] text-white uppercase">
          BF-Manager
        </span>
      </Link>

      {NAV_GROUPS.map((group) => {
        if (group.adminOnly && !isAdmin) return null;
        return (
          <div key={group.title ?? "_main"} className="mt-2">
            {group.title ? (
              <div className="text-muted-foreground/70 mb-1.5 px-3 text-[11px] font-medium tracking-[0.18em] uppercase">
                {group.title}
              </div>
            ) : null}
            {group.items.map((item) => {
              const active = pathname.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavClick}
                  className={cn(
                    "relative flex items-center gap-3 rounded-sm px-3 py-2 text-sm transition-colors",
                    "before:bg-foreground before:absolute before:top-1/2 before:left-0 before:h-5 before:w-[3px] before:-translate-y-1/2 before:transition-opacity",
                    active
                      ? "text-foreground bg-white/10 font-medium before:opacity-100"
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
