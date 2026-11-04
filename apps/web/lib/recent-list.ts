/**
 * 「最近查看」列表：存在浏览器 localStorage，打开详情页时写入，查询页空态时展示。
 * 每个游戏一份，各自定义存哪几项（只存展示用的字段，不涉及隐私）。
 */

import { useMemo, useSyncExternalStore } from "react";

const LIMIT = 8;

export function createRecentList<T>(key: string, idOf: (item: T) => number) {
  const listeners = new Set<() => void>();

  function readRaw(): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function parse(raw: string | null): T[] {
    try {
      const list = JSON.parse(raw ?? "[]");
      return Array.isArray(list) ? list.slice(0, LIMIT) : [];
    } catch {
      return [];
    }
  }

  function write(list: T[] | null): void {
    try {
      if (list) localStorage.setItem(key, JSON.stringify(list));
      else localStorage.removeItem(key);
    } catch {
      // 隐私模式 / 存储已满时放弃记录，不影响页面
    }
    listeners.forEach((l) => l());
  }

  function subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    push(item: T): void {
      const rest = parse(readRaw()).filter((r) => idOf(r) !== idOf(item));
      write([item, ...rest].slice(0, LIMIT));
    },
    clear(): void {
      write(null);
    },
    /** 服务端渲染时为空列表，挂载后读到本机记录；清除后即时刷新 */
    useList(): T[] {
      const raw = useSyncExternalStore(subscribe, readRaw, () => null);
      return useMemo(() => parse(raw), [raw]);
    },
  };
}
