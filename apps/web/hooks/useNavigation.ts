"use client";

/**
 * 站内连贯导航：
 * - useBack：详情页「返回」回到真正来的那一页（保留搜索词、筛选），直接打开链接进来时才退到列表页。
 * - usePageState：列表页的筛选等状态在站内来回跳转时保留。
 *
 * 两者都只记在客户端模块内存里：站内跳转（客户端渲染）时能读到，刷新或新开标签页时从空开始，
 * 与服务端渲染的初始值一致，不会出现水合不一致。
 */

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

// 站内访问过的路径栈；后退回上一个路径时出栈，否则入栈
const visited: string[] = [];
const pageState = new Map<string, unknown>();

/** 在应用外壳里调用一次，记录站内路径变化 */
export function useTrackNavigation(): void {
  const pathname = usePathname();
  useEffect(() => {
    if (visited[visited.length - 1] === pathname) return;
    if (visited[visited.length - 2] === pathname) visited.pop();
    else visited.push(pathname);
  }, [pathname]);
}

/** 返回上一页；本次会话里没有站内上一页（直接打开、新标签页）时跳到 fallback */
export function useBack(fallback: string): () => void {
  const router = useRouter();
  return useCallback(() => {
    if (visited.length > 1) router.back();
    else router.push(fallback);
  }, [router, fallback]);
}

/** 与 useState 相同，但值按 key 记住，离开页面再回来时恢复 */
export function usePageState<T>(
  key: string,
  initial: T,
): [T, (next: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() =>
    pageState.has(key) ? (pageState.get(key) as T) : initial,
  );
  const set = useCallback(
    (next: T | ((prev: T) => T)) =>
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        pageState.set(key, resolved);
        return resolved;
      }),
    [key],
  );
  return [value, set];
}
