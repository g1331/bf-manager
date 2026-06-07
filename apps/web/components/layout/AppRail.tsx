"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Globe } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";
import { MODULES, isModuleActive, type RailModule } from "@/lib/nav";

/**
 * 左侧窄图标条（rail），复刻经典战地大厅左侧的图标竖条：
 *   图标组从顶部留白后开始（偏上排布），游戏在前、玩家信息与管理紧随其后；
 *   系统区入口（门户首页）钉在最底，对应大厅的电源 / 关闭位。
 *   游戏以封面缩略图呈现，其它模块用线性图标；激活态以左侧橙刻线标记，
 *   悬停浮出名称提示；未启用游戏灰显且不可点击。
 * rail 本身不铺卡片背景，直接浮于战场氛围之上，与内容靠外层的局部竖线分隔。
 */
export function AppRail() {
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
    // 主图标组重心落在视口上 1/3（贴近真实大厅约 39% 处），底部系统区绝对钉底
    <nav className="relative flex h-full flex-col items-center pt-[22vh]">
      {/* 主图标组：游戏 + 玩家 / 管理 */}
      <div className="flex flex-col items-center">
        <div className="flex flex-col items-center gap-2">
          {games.map((m) => (
            <RailLink key={m.key} module={m} active={isModuleActive(pathname, m)} />
          ))}
        </div>
        {player.length > 0 ? (
          <>
            <span className="my-4 h-px w-8 bg-white/15" aria-hidden />
            <div className="flex flex-col items-center gap-2">
              {player.map((m) => (
                <RailLink key={m.key} module={m} active={isModuleActive(pathname, m)} />
              ))}
            </div>
          </>
        ) : null}
      </div>

      {/* 底部系统区：门户首页，绝对定位钉底 */}
      <Link
        href="/"
        className="group absolute bottom-6 left-1/2 flex size-12 -translate-x-1/2 items-center justify-center text-white/45 transition-colors hover:text-white"
      >
        <Globe className="size-5" />
        <RailTooltip>门户首页</RailTooltip>
      </Link>
    </nav>
  );
}

/** rail 单项：激活左刻线 + 悬停提示；游戏缩略图与图标两种形态。 */
function RailLink({ module: m, active }: { module: RailModule; active: boolean }) {
  const Icon = m.icon;

  const inner = (
    <>
      {/*
       * 激活竖线：复刻真实大厅的选中方式——独立于图标的橙竖线位于缩略图左侧，
       * 与图标之间留出约 9px 间隔（-left-3，竖线宽 3px），不叠在图标上。
       * 图标本身不加 ring / 边框等装饰，只通过这条竖线表达选中。
       */}
      <span
        className={cn(
          "absolute top-1/2 -left-3 h-12 w-[3px] -translate-y-1/2 bg-amber-500 transition-opacity",
          active ? "opacity-100" : "opacity-0",
        )}
        aria-hidden
      />
      {m.kind === "game" && m.image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={m.image}
          alt=""
          className={cn(
            "size-14 rounded-sm object-cover transition-opacity",
            m.disabled
              ? "opacity-35 grayscale"
              : active
                ? "opacity-100"
                : "opacity-70 group-hover:opacity-100",
          )}
        />
      ) : Icon ? (
        <Icon
          className={cn(
            "size-6 transition-colors",
            active ? "text-amber-500" : "text-white/55 group-hover:text-white",
          )}
        />
      ) : null}
      <RailTooltip>{m.label}</RailTooltip>
    </>
  );

  // 链接收紧包住缩略图并在 rail 内居中；激活竖线 absolute -left-3 落在缩略图左侧
  const baseClass = "group relative flex h-14 w-full items-center justify-center transition-colors";

  if (m.disabled || m.href === "#") {
    return (
      <span className={cn(baseClass, "cursor-not-allowed")} aria-disabled="true">
        {inner}
      </span>
    );
  }

  return (
    <Link href={m.href} className={baseClass}>
      {inner}
    </Link>
  );
}

/** rail 悬停提示标签：纯 CSS，悬停时从图标右侧浮出。 */
function RailTooltip({ children }: { children: React.ReactNode }) {
  return (
    <span
      role="tooltip"
      className="pointer-events-none absolute left-full z-50 ml-1 hidden border border-white/15 bg-black/90 px-2 py-1 text-xs font-medium whitespace-nowrap text-white opacity-0 transition-opacity group-hover:opacity-100 lg:block"
    >
      {children}
    </span>
  );
}
