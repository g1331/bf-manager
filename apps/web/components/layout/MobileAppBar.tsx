"use client";

import { usePathname } from "next/navigation";
import { ChevronLeft, Menu } from "lucide-react";
import { useBack } from "@/hooks/useNavigation";
import { UserMenu } from "./UserMenu";

/**
 * 手机端顶栏：吸顶、48px 高，按原生 App 的导航栏来做。
 *   - 列表 / 模块页：左侧菜单键打开一级模块抽屉，中间是厂牌字标；
 *   - 详情页：左侧换成返回键（回到真正来的那一页，直接打开时退到列表），中间是页面名。
 * 详情页自己的「返回」按钮只在桌面端显示。
 */
const DETAIL_ROUTES: Array<{ prefix: string | RegExp; title: string; fallback: string }> = [
  { prefix: "/bf1/server/", title: "服务器", fallback: "/bf1/servers" },
  { prefix: "/bf1/player/", title: "玩家战绩", fallback: "/bf1/players" },
  { prefix: "/bf1/platoon/", title: "战队", fallback: "/bf1/platoons" },
  { prefix: "/me/groups/", title: "群组", fallback: "/me/groups" },
  // 图鉴下的分区列表（/bf1/codex/medals 等）不算详情页，只有百科条目 c003、cxp113 这类才是
  { prefix: /^\/bf1\/codex\/c[a-z]*\d/, title: "百科", fallback: "/bf1/codex" },
];

export function getDetailRoute(pathname: string) {
  return (
    DETAIL_ROUTES.find((r) =>
      typeof r.prefix === "string" ? pathname.startsWith(r.prefix) : r.prefix.test(pathname),
    ) ?? null
  );
}

export function MobileAppBar({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const detail = getDetailRoute(pathname);
  const back = useBack(detail?.fallback ?? "/stats");

  return (
    <header className="sticky top-0 z-40 flex h-12 items-center gap-1 border-b border-white/[0.07] bg-black/75 px-1.5 backdrop-blur-md lg:hidden">
      {detail ? (
        <button
          type="button"
          onClick={back}
          aria-label="返回"
          className="flex size-11 items-center justify-center text-white/80 active:text-white"
        >
          <ChevronLeft className="size-6" />
        </button>
      ) : (
        <button
          type="button"
          onClick={onMenu}
          aria-label="打开导航菜单"
          className="flex size-11 items-center justify-center text-white/80 active:text-white"
        >
          <Menu className="size-5" />
        </button>
      )}

      <div className="min-w-0 flex-1">
        {detail ? (
          <span className="block truncate text-[17px] font-semibold text-white">
            {detail.title}
          </span>
        ) : (
          <span className="font-display flex items-center gap-2 text-[15px] font-semibold tracking-[0.2em] text-white uppercase">
            <span className="h-4 w-[3px] bg-amber-500" aria-hidden />
            BF-Manager
          </span>
        )}
      </div>

      <div className="flex items-center pr-1.5">
        <UserMenu compact />
      </div>
    </header>
  );
}
