"use client";

import { motion } from "framer-motion";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import type { ServerMapStat } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";
import { formatDuration } from "./history";

const LIST_LIMIT = 8;

/**
 * 近 7 天热门地图：按「人·分钟」（每分钟在线人数累加）排名，比单纯时长更能体现哪张图
 * 真正留得住人。色块与 24 小时战况的地图时间轴同色。
 */
export function MapStatsPanel({
  stats,
  colors,
  currentMap,
}: {
  stats: ServerMapStat[];
  colors: Record<string, string>;
  currentMap: string | null;
}) {
  const items = stats.slice(0, LIST_LIMIT);
  const top = Math.max(items[0]?.player_minutes ?? 0, 1);
  const total = stats.reduce((s, m) => s + m.player_minutes, 0) || 1;
  const totalMinutes = stats.reduce((s, m) => s + m.minutes, 0);

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-black/45 p-5 backdrop-blur-sm sm:p-6"
    >
      <div className="flex items-baseline justify-between gap-3">
        <SectionHeading className="mb-0">热门地图</SectionHeading>
        <span className="text-[11px] text-white/40">
          近 7 天 · 有人 {formatDuration(totalMinutes)}
        </span>
      </div>

      <ol className="mt-4 flex-1 space-y-2.5">
        {items.map((m, i) => {
          const share = (m.player_minutes / total) * 100;
          const isCurrent = m.map_name === currentMap;
          return (
            <li key={`${m.map_name}-${m.game_mode}`} className="flex items-center gap-3">
              <span
                className={cn(
                  "font-display w-5 shrink-0 text-center text-base font-bold tabular-nums",
                  i < 3 ? "text-amber-400" : "text-white/30",
                )}
              >
                {i + 1}
              </span>
              <div className="relative h-11 w-[4.5rem] shrink-0 overflow-hidden [clip-path:polygon(0_0,100%_0,100%_calc(100%-8px),calc(100%-8px)_100%,0_100%)]">
                {m.map_image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={m.map_image_url}
                    alt=""
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="h-full w-full bg-white/[0.06]" />
                )}
                <span
                  className="absolute inset-y-0 left-0 w-1"
                  style={{ background: colors[m.map_name] }}
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="truncate text-sm font-medium text-white">
                    {m.map_display_name ?? m.map_name}
                  </span>
                  {m.mode_display_name ? (
                    <span className="shrink-0 text-[11px] text-white/45">
                      {m.mode_display_name}
                    </span>
                  ) : null}
                  {isCurrent ? (
                    <span className="shrink-0 bg-amber-400 px-1 text-[10px] leading-4 font-bold text-black">
                      当前
                    </span>
                  ) : null}
                  <span className="ml-auto shrink-0 text-xs text-white/70 tabular-nums">
                    {share.toFixed(0)}%
                  </span>
                </div>
                <div className="mt-1.5 h-1 bg-white/[0.07]">
                  <motion.div
                    className="h-full"
                    style={{ background: colors[m.map_name] }}
                    initial={{ width: 0 }}
                    animate={{ width: `${(m.player_minutes / top) * 100}%` }}
                    transition={{ duration: 0.9, delay: i * 0.05, ease: "easeOut" }}
                  />
                </div>
                <div className="mt-1 flex gap-3 text-[11px] text-white/45 tabular-nums">
                  <span>{formatDuration(m.minutes)}</span>
                  <span>平均 {m.avg_players.toFixed(0)} 人</span>
                  <span>{m.rounds} 轮</span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {stats.length > LIST_LIMIT ? (
        <div className="mt-3 text-[11px] text-white/35">
          另有 {stats.length - LIST_LIMIT} 张图未列出
        </div>
      ) : null}
    </Bf1Panel>
  );
}
