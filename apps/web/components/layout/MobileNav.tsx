"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Globe } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";
import { MODULES, isModuleActive, type RailModule } from "@/lib/nav";

/**
 * 移动端一级导航列表，置于左侧抽屉（Sheet）中。
 * 与桌面 rail 共用 MODULES 数据，但以「图标 + 文字」宽列表呈现，便于触摸切换模块；
 * 完成模块切换后由 onNavClick 关闭抽屉。二级 tab 在抽屉之外的顶部横条始终可见。
 * 抽屉中不强制居中，按 games → player 两组顺序排列，底部固定门户首页。
 */
export function MobileNav({ onNavClick }: { onNavClick?: () => void }) {
  const pathname = usePathname();
  const session = useSession();
  const isLoggedIn = !!session.data;
  const isAdmin = session.data?.role === "admin";

  const visible = MODULES.filter((m) => {
    if (m.adminOnly) return isAdmin;
    if (m.authOnly) return isLoggedIn;
    return true;
  });

  const games = visible.filter((m) => m.section === "games");
  const player = visible.filter((m) => m.section === "player");

  return (
    <nav className="flex h-full flex-col px-3 py-4">
      {/* 品牌区：橙刻线 + 大写厂牌，底部细线分隔 */}
      <div className="mb-3 flex items-center gap-2.5 border-b border-white/10 px-2 pb-4">
        <span className="h-5 w-[3px] shrink-0 bg-amber-500" />
        <span className="font-display text-base font-semibold tracking-[0.18em] text-white uppercase">
          BF-Manager
        </span>
      </div>

      <div className="flex flex-col gap-0.5">
        {games.map((m) => (
          <MobileNavItem
            key={m.key}
            module={m}
            active={isModuleActive(pathname, m)}
            onNavClick={onNavClick}
          />
        ))}
      </div>

      {player.length > 0 ? (
        <>
          <span className="my-3 h-px w-full bg-white/10" aria-hidden />
          <div className="flex flex-col gap-0.5">
            {player.map((m) => (
              <MobileNavItem
                key={m.key}
                module={m}
                active={isModuleActive(pathname, m)}
                onNavClick={onNavClick}
              />
            ))}
          </div>
        </>
      ) : null}

      <Link
        href="/"
        onClick={onNavClick}
        className="mt-auto flex items-center gap-3 px-2 py-2.5 text-sm text-white/55 transition-colors hover:text-white"
      >
        <Globe className="size-5 shrink-0" />
        门户首页
      </Link>
    </nav>
  );
}

function MobileNavItem({
  module: m,
  active,
  onNavClick,
}: {
  module: RailModule;
  active: boolean;
  onNavClick?: () => void;
}) {
  const Icon = m.icon;

  const content = (
    <>
      {m.kind === "game" && m.image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={m.image}
          alt=""
          className={cn(
            "size-7 shrink-0 rounded-sm object-cover",
            m.disabled ? "opacity-35 grayscale" : "ring-1 ring-white/15",
          )}
        />
      ) : Icon ? (
        <Icon className="size-5 shrink-0" />
      ) : null}
      <span className="truncate">{m.label}</span>
    </>
  );

  const baseClass = cn(
    "relative flex items-center gap-3 px-2 py-2.5 text-sm transition-colors",
    "before:absolute before:top-1/2 before:left-0 before:h-6 before:w-[3px] before:-translate-y-1/2 before:bg-amber-500 before:transition-opacity",
    active
      ? "font-medium text-amber-500 before:opacity-100"
      : "text-white/65 hover:text-white before:opacity-0",
  );

  if (m.disabled || m.href === "#") {
    return (
      <span className={cn(baseClass, "cursor-not-allowed text-white/35")} aria-disabled="true">
        {content}
      </span>
    );
  }

  return (
    <Link href={m.href} onClick={onNavClick} className={baseClass}>
      {content}
    </Link>
  );
}
