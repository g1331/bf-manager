/**
 * 战绩查询「最近查看」：存在浏览器 localStorage，打开玩家详情页时写入，
 * 查询页空态时展示。只存展示用的三项，不涉及任何隐私字段。
 */

import { useMemo, useSyncExternalStore } from "react";

export interface RecentPlayer {
  persona_id: number;
  display_name: string;
  avatar_url: string | null;
}

const KEY = "bf1:recent-players";
const LIMIT = 8;
const listeners = new Set<() => void>();

function readRaw(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function parse(raw: string | null): RecentPlayer[] {
  try {
    const list = JSON.parse(raw ?? "[]");
    return Array.isArray(list) ? list.slice(0, LIMIT) : [];
  } catch {
    return [];
  }
}

function write(list: RecentPlayer[] | null): void {
  try {
    if (list) localStorage.setItem(KEY, JSON.stringify(list));
    else localStorage.removeItem(KEY);
  } catch {
    // 隐私模式 / 存储已满时放弃记录，不影响页面
  }
  listeners.forEach((l) => l());
}

export function pushRecentPlayer(p: RecentPlayer): void {
  const rest = parse(readRaw()).filter((r) => r.persona_id !== p.persona_id);
  write([p, ...rest].slice(0, LIMIT));
}

export function clearRecentPlayers(): void {
  write(null);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 服务端渲染时为空列表，挂载后读到本机记录；清除后即时刷新 */
export function useRecentPlayers(): RecentPlayer[] {
  const raw = useSyncExternalStore(subscribe, readRaw, () => null);
  return useMemo(() => parse(raw), [raw]);
}
