"use client";

import { useEffect, useState } from "react";

/** 响应式 media query hook，SSR 安全 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(query);
    // SSR 安全：render 阶段访问不到 window.matchMedia，初始 matches 只能在 effect 内补读。
    // react-compiler 的 set-state-in-effect 规则对这种「挂载后同步外部状态」误报，按行豁免。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMatches(mq.matches);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

/** 桌面端断点（>= 1024px） */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}

/** 平板及以上（>= 768px） */
export function useIsTablet(): boolean {
  return useMediaQuery("(min-width: 768px)");
}
