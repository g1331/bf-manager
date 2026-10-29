"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface SectionTab<K extends string> {
  key: K;
  label: string;
  count?: number;
}

/**
 * 详情页的吸顶分区导航：琥珀下划线随切换滑动，翻长列表时也能随时切分区。
 * 手机端吸在 48px 顶栏下方（top-12）；分区多时横向滑动，选中项自动滑到中间，不会半截露在屏幕外。
 */
export function SectionNav<K extends string>({
  tabs,
  tab,
  onTab,
}: {
  tabs: ReadonlyArray<SectionTab<K>>;
  tab: K;
  onTab: (t: K) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = scroller.current;
    const el = box?.querySelector<HTMLElement>('[aria-current="true"]');
    if (!box || !el || box.scrollWidth <= box.clientWidth) return;
    box.scrollTo({
      left: el.offsetLeft - (box.clientWidth - el.offsetWidth) / 2,
      behavior: "smooth",
    });
  }, [tab]);

  return (
    <nav className="sticky top-12 z-20 mt-4 border-b border-white/10 bg-black/70 backdrop-blur-md sm:mt-6 lg:top-0">
      <div
        ref={scroller}
        className="relative flex [scrollbar-width:none] gap-1 overflow-x-auto [&::-webkit-scrollbar]:hidden"
      >
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-current={tab === t.key}
            onClick={() => onTab(t.key)}
            className={cn(
              "relative flex shrink-0 items-baseline gap-1.5 px-3 py-3 text-[15px] font-semibold tracking-[0.06em] transition-colors lg:px-4 lg:py-3.5 lg:tracking-[0.15em]",
              tab === t.key ? "text-white" : "text-white/45 hover:text-white/80",
            )}
          >
            {t.label}
            {t.count != null ? (
              <span
                className={cn(
                  "text-[11px] font-medium tracking-normal tabular-nums",
                  tab === t.key ? "text-amber-400" : "text-white/35",
                )}
              >
                {t.count}
              </span>
            ) : null}
            {tab === t.key ? (
              <motion.span
                layoutId="section-nav-underline"
                className="absolute inset-x-3 bottom-0 h-0.5 bg-amber-400"
              />
            ) : null}
          </button>
        ))}
      </div>
    </nav>
  );
}

/**
 * 当前分区记在地址栏 hash 里（#weapons），刷新、分享链接都能回到同一分区。
 * 调用方须保证组件只在客户端挂载（数据到手后才渲染），初始值直接读 window。
 * 不在 available 里的分区（如未登录时的审计）回落到第一个分区。
 */
export function useTabHash<K extends string>(all: readonly K[], available: readonly K[]) {
  const first = all[0];
  const [tab, setTabState] = useState<K>(() => {
    const fromHash = window.location.hash.slice(1) as K;
    return all.includes(fromHash) ? fromHash : first;
  });
  const setTab = (t: K) => {
    setTabState(t);
    window.history.replaceState(null, "", t === first ? window.location.pathname : `#${t}`);
  };
  return [available.includes(tab) ? tab : first, setTab] as const;
}
