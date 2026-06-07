"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { getNavContext, isTabActive } from "@/lib/nav";

/**
 * 顶部横向二级 tab，复刻经典战地大厅顶部的标签栏：
 *   tab 单行中文主标、正常字重、间距较宽（呼应真实大厅 56-64px 视距）；
 *   下方有一条贯穿全宽的细底线作为「轨道」，激活段以与文字等宽的发光白线叠加其上；
 *   切换 tab 时激活段滑动跟随（animated 模式）。
 * tab 集由当前路径所属的一级模块决定（见 getNavContext）；无 tab 时不渲染。
 * 桌面端嵌在 header 内（animated），移动端单独成行可横向滚动，两端共用本组件。
 */
export function TopTabs({
  className,
  animated = false,
}: {
  className?: string;
  animated?: boolean;
}) {
  const pathname = usePathname();
  const { tabs } = getNavContext(pathname);

  if (tabs.length === 0) return null;

  return (
    <div
      className={cn(
        // relative 承载贯穿底线，flex-1 让贯穿线一直延伸到右侧 logo 之前
        "relative flex flex-1 items-stretch",
        className,
      )}
    >
      <nav
        className={cn(
          "relative z-10 flex items-end gap-14 overflow-x-auto",
          // 隐藏横向滚动条，保留可滚动能力（移动端）
          "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        )}
      >
        {tabs.map((tab) => {
          const active = isTabActive(pathname, tab);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "group relative flex shrink-0 items-center py-2 transition-colors",
                active ? "text-white" : "text-white/65 hover:text-white",
              )}
            >
              <span className="text-[22px] font-normal whitespace-nowrap">{tab.label}</span>
              {/* 激活段：与文字等宽的发光白线，叠在贯穿底线之上 */}
              {active ? (
                animated ? (
                  <motion.span
                    layoutId="top-tab-underline"
                    className="absolute inset-x-0 -bottom-px h-[2px] bg-white shadow-[0_0_8px_rgba(255,255,255,0.85)]"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    aria-hidden
                  />
                ) : (
                  <span
                    className="absolute inset-x-0 -bottom-px h-[2px] bg-white shadow-[0_0_8px_rgba(255,255,255,0.85)]"
                    aria-hidden
                  />
                )
              ) : null}
            </Link>
          );
        })}
      </nav>
      {/* 贯穿底线「轨道」：填满整个 tab 栏宽度，激活段叠加其上 */}
      <span
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-white/15"
        aria-hidden
      />
    </div>
  );
}
