import { useEffect, useState } from "react";
import type { ServerPlayerCountPoint } from "@/lib/api/bf1";

/** 相邻采样点间隔超过它就视为断档（服务器空了不采样）；留出余量兼容早期每 5 分钟一次的采样 */
export const GAP_SECONDS = 420;

/** 地图时间轴上的一段：同一张图（地图 + 模式）连续采样的区间，end 为最后一个点 + 1 分钟 */
export interface MapSegment {
  key: string;
  mapName: string;
  mode: string | null;
  start: number;
  end: number;
  peak: number;
  avg: number;
}

export function mapKey(mapName: string, mode: string | null): string {
  return `${mapName}|${mode ?? ""}`;
}

/** 按「换图或断档」把采样点切成地图段 */
export function toMapSegments(points: ServerPlayerCountPoint[]): MapSegment[] {
  const out: MapSegment[] = [];
  let cur: (MapSegment & { sum: number; n: number }) | null = null;
  let prevTs = 0;
  for (const p of points) {
    const key = p.map_name ? mapKey(p.map_name, p.game_mode) : null;
    const broken = cur === null || key !== cur.key || p.ts - prevTs > GAP_SECONDS;
    if (broken && cur) {
      out.push({ ...cur, avg: cur.sum / cur.n });
      cur = null;
    }
    if (key && p.map_name) {
      if (!cur) {
        cur = {
          key,
          mapName: p.map_name,
          mode: p.game_mode,
          start: p.ts,
          end: p.ts + 60,
          peak: 0,
          avg: 0,
          sum: 0,
          n: 0,
        };
      }
      cur.end = p.ts + 60;
      cur.peak = Math.max(cur.peak, p.players);
      cur.sum += p.players;
      cur.n += 1;
    }
    prevTs = p.ts;
  }
  if (cur) out.push({ ...cur, avg: cur.sum / cur.n });
  return out;
}

/** 地图配色：在深色背景上可辨、不抢琥珀主色的一组低饱和战场色 */
const MAP_PALETTE = [
  "#d4a72c",
  "#7fa35c",
  "#c2693c",
  "#5f93ad",
  "#a68b66",
  "#8f73ad",
  "#4f9e8d",
  "#b34d4d",
  "#a0a86e",
  "#6b80b8",
];

/**
 * 按出现顺序给地图分色（热门地图榜在前，时间轴里多出来的图在后），同一张图在时间轴与
 * 热门地图榜里颜色一致；超出色板后循环。
 */
export function buildMapColors(mapNames: string[]): Record<string, string> {
  const colors: Record<string, string> = {};
  for (const name of mapNames) {
    if (!(name in colors)) {
      colors[name] = MAP_PALETTE[Object.keys(colors).length % MAP_PALETTE.length];
    }
  }
  return colors;
}

export function formatClock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${Math.max(1, Math.round(minutes))} 分钟`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`;
}

/** 当前 unix 秒，按 intervalMs 刷新；渲染里不能直接调 Date.now() */
export function useNowSeconds(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const timer = setInterval(() => setNow(Math.floor(Date.now() / 1000)), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
