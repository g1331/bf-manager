"use client";

/**
 * 服务器区子标签：复刻游戏「遊戲 / 我的最愛 / 最近遊玩 / 您的伺服器」。
 * 「游戏」=全量服务器浏览器，「您的服务器」=当前用户有服管角色的服。中间两项依赖玩家账号维度
 * 的收藏 / 历史数据，暂未接入，置灰不可点。服务器浏览页与「我的服务器」页共用本组件。
 * 手机端两页各有底部标签栏入口，整组不显示。
 */

import Link from "next/link";
import { cn } from "@/lib/utils";

type SubTab = "browse" | "mine";

export function ServerSubTabs({ game, active }: { game: string; active: SubTab }) {
  const tabs = [
    { key: "browse" as const, label: "游戏", href: `/${game}/servers`, enabled: true },
    { key: "fav", label: "我的最爱", href: null, enabled: false },
    { key: "recent", label: "最近游玩", href: null, enabled: false },
    { key: "mine" as const, label: "您的服务器", href: `/${game}/my-servers`, enabled: true },
  ];
  return (
    <nav className="hidden [scrollbar-width:none] items-stretch gap-6 overflow-x-auto border-b border-white/10 text-sm lg:flex lg:shrink-0 [&::-webkit-scrollbar]:hidden">
      {tabs.map((t) => {
        if (!t.enabled || !t.href) {
          return (
            <span
              key={t.key}
              title="需玩家账号维度数据，暂未接入"
              className="flex h-11 shrink-0 cursor-default items-center font-medium tracking-wide whitespace-nowrap text-white/30"
            >
              {t.label}
            </span>
          );
        }
        const isActive = t.key === active;
        return (
          <Link
            key={t.key}
            href={t.href}
            className={cn(
              "relative flex h-11 shrink-0 items-center font-medium tracking-wide whitespace-nowrap",
              isActive ? "text-white" : "cursor-pointer text-white/55 hover:text-white",
            )}
          >
            {t.label}
            {isActive ? (
              <span className="absolute bottom-0 left-0 h-0.5 w-full bg-amber-400" />
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
